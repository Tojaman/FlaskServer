# 원래 깃허브 주소
# https://github.com/SociallyIneptWeeb/AICoverGen.git

import argparse
import gc
import hashlib
import json
import os
import shlex
import subprocess
from contextlib import suppress
from urllib.parse import urlparse, parse_qs

import gradio as gr
import librosa
import numpy as np
import soundfile as sf
import sox
import yt_dlp
from pedalboard import Pedalboard, Reverb, Compressor, HighpassFilter
from pedalboard.io import AudioFile
from pydub import AudioSegment

from mdx import run_mdx
from rvc import Config, load_hubert, get_vc, rvc_infer

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

mdxnet_models_dir = os.path.join(BASE_DIR, 'mdxnet_models')
rvc_models_dir = os.path.join(BASE_DIR, 'rvc_models')
output_dir = os.path.join(BASE_DIR, 'song_output')


def raise_exception(error_msg, is_webui):
    if is_webui:
        raise gr.Error(error_msg)
    else:
        raise Exception(error_msg)


def get_rvc_model(voice_model, is_webui):
    rvc_model_filename, rvc_index_filename = None, None
    model_dir = os.path.join(rvc_models_dir, voice_model)
    for file in os.listdir(model_dir):
        ext = os.path.splitext(file)[1]
        # 모델
        if ext == '.pth':
            rvc_model_filename = file
        # index 파일(설정 파일)
        if ext == '.index':
            rvc_index_filename = file

    if rvc_model_filename is None:
        error_msg = f'No model file exists in {model_dir}.'
        raise_exception(error_msg, is_webui)

    return os.path.join(model_dir, rvc_model_filename), os.path.join(model_dir, rvc_index_filename) if rvc_index_filename else ''


def get_audio_paths(song_dir):
    orig_song_path = None
    instrumentals_path = None
    main_vocals_dereverb_path = None
    backup_vocals_path = None

    for file in os.listdir(song_dir):
        if file.endswith('_Instrumental.wav'):
            instrumentals_path = os.path.join(song_dir, file)
            orig_song_path = instrumentals_path.replace('_Instrumental', '')

        elif file.endswith('_Vocals_Main_DeReverb.wav'):
            main_vocals_dereverb_path = os.path.join(song_dir, file)
#

        elif file.endswith('_Vocals_Backup.wav'):
            backup_vocals_path = os.path.join(song_dir, file)

    return orig_song_path, instrumentals_path, main_vocals_dereverb_path, backup_vocals_path

# 음성 파일을 스테레오로 변환하는 함수
def convert_to_stereo(audio_path):
    # mono=False : 스테레오 오디오 로드하도록 저장
    # sr=44100 : 샘플링 속도 44100HZ로 설정
    wave, sr = librosa.load(audio_path, mono=False, sr=44100)

    # 오디오 파일이 모노인 경우 스테레오로 변환하여 반환
    if type(wave[0]) != np.ndarray:
        stereo_path = f'{os.path.splitext(audio_path)[0]}_stereo.wav'
        command = shlex.split(f'ffmpeg -y -loglevel error -i "{audio_path}" -ac 2 -f wav "{stereo_path}"')
        subprocess.run(command)
        return stereo_path
    # 오디오 파일이 스테레오인 경우 그대로 반환
    else:
        return audio_path


def pitch_shift(audio_path, pitch_change):
    output_path = f'{os.path.splitext(audio_path)[0]}_p{pitch_change}.wav'
    if not os.path.exists(output_path):
        y, sr = sf.read(audio_path)
        tfm = sox.Transformer()
        tfm.pitch(pitch_change)
        y_shifted = tfm.build_array(input_array=y, sample_rate_in=sr)
        sf.write(output_path, y_shifted, sr)

    return output_path


# 로컬 파일 경로에서 hash값(음성 ID)
def get_hash(filepath):
    with open(filepath, 'rb') as f:
        file_hash = hashlib.blake2b()
        while chunk := f.read(8192):
            file_hash.update(chunk)

    return file_hash.hexdigest()[:11]


def display_progress(message, percent, is_webui, progress=None):
    if is_webui:
        progress(percent, desc=message)
    else:
        print(message)


# 오디오 전처리
# 우리 프로젝트에선 백업 보컬, 악기가 없으므로 전처리가 필요 없을 것 같다.
def preprocess_song(song_input, mdx_model_params, song_id, is_webui, input_type, progress=None):
    keep_orig = False
    if input_type == 'local':
        orig_song_path = song_input
        keep_orig = True
    else:
        orig_song_path = None

    song_output_dir = os.path.join(output_dir, song_id)
    
    
    # 우리 프로젝트에선 백업 보컬, 배경 악기 .. 등이 없고 오로지 사람의 음성만 있다.
    # 따라서 보컬, 백업 보컬, 악기를 분리하는 함수( run_mdx() )를 사용하지 않고원래 음성 파일 경로를 그대로 사용하면 된다.
    
    # 참고, run_mdx() 함수는 mdx.py에 정의된 함수이다.(original 음성 파일에서 보컬과 백업 보컬, 악기를 분리하여 파일을 경로하는 함수)
    orig_song_path = convert_to_stereo(orig_song_path)


    display_progress('[~] Separating Vocals from Instrumental...', 0.1, is_webui, progress)
    # vocals_path, instrumentals_path 파일의 경로
    vocals_path, instrumentals_path = run_mdx(mdx_model_params, song_output_dir, os.path.join(mdxnet_models_dir, 'UVR-MDX-NET-Voc_FT.onnx'), orig_song_path, denoise=True, keep_orig=keep_orig)

    display_progress('[~] Separating Main Vocals from Backup Vocals...', 0.2, is_webui, progress)
    backup_vocals_path, main_vocals_path = run_mdx(mdx_model_params, song_output_dir, os.path.join(mdxnet_models_dir, 'UVR_MDXNET_KARA_2.onnx'), vocals_path, suffix='Backup', invert_suffix='Main', denoise=True)

    display_progress('[~] Applying DeReverb to Vocals...', 0.3, is_webui, progress)
    # main_vocals_dereverb_path : 보컬에서 리버브 효과 제거
    _, main_vocals_dereverb_path = run_mdx(mdx_model_params, song_output_dir, os.path.join(mdxnet_models_dir, 'Reverb_HQ_By_FoxJoy.onnx'), main_vocals_path, invert_suffix='DeReverb', exclude_main=True, denoise=True)

    return orig_song_path, vocals_path, instrumentals_path, main_vocals_path, backup_vocals_path, main_vocals_dereverb_path

    # ----------우리 프로젝트에서 사용할 코드---------- #
    # orig_song_path = convert_to_stereo(orig_song_path)
    
    # return orig_song_path
    # ------------------------------------------------ #


# RVC 처리(음성 변환)를 진행하는 핵심 함수이다.
# output_path에 RVC로 변환된 음성 파일이 저장된다.
def voice_change(voice_model, vocals_path, output_path, pitch_change, f0_method, index_rate, filter_radius, rms_mix_rate, protect, crepe_hop_length, is_webui):
    rvc_model_path, rvc_index_path = get_rvc_model(voice_model, is_webui)
    device = 'cuda:0'
    config = Config(device, True)
    hubert_model = load_hubert(device, config.is_half, os.path.join(rvc_models_dir, 'hubert_base.pt'))
    
    # get_vc : vc(Voice Conversion) 관련 모델과 기타 관련 설정들 초기화
    cpt, version, net_g, tgt_sr, vc = get_vc(device, config.is_half, config, rvc_model_path)

    # vocals_path에 있는 vocal 파일의 음성을 변환하여 output_path에 변환된 음성 파일을 생성
    rvc_infer(rvc_index_path, index_rate, vocals_path, output_path, pitch_change, f0_method, cpt, version, net_g, filter_radius, tgt_sr, rms_mix_rate, protect, crepe_hop_length, vc, hubert_model)
    del hubert_model, cpt
    gc.collect()

# 이건 잘 모르겠다.
def add_audio_effects(audio_path, reverb_rm_size, reverb_wet, reverb_dry, reverb_damping):
    output_path = f'{os.path.splitext(audio_path)[0]}_mixed.wav'

    # Initialize audio effects plugins
    board = Pedalboard(
        [
            HighpassFilter(),
            Compressor(ratio=4, threshold_db=-15),
            Reverb(room_size=reverb_rm_size, dry_level=reverb_dry, wet_level=reverb_wet, damping=reverb_damping)
         ]
    )

    with AudioFile(audio_path) as f:
        with AudioFile(output_path, 'w', f.samplerate, f.num_channels) as o:
            # Read one second of audio at a time, until the file is empty:
            while f.tell() < f.frames:
                chunk = f.read(int(f.samplerate))
                effected = board(chunk, f.samplerate, reset=False)
                o.write(effected)

    return output_path

# AI 보컬과 악기를 결합하여 최종 커버 곡을 생성(우리 프로젝트에선 악기가 따로 없으므로 이 함수는 필요 없을 것으로 예상)
def combine_audio(audio_paths, output_path, main_gain, backup_gain, inst_gain, output_format):
    # 아래 main_vocal_audio, backup_vocal_audio, instrumental_audio 세 파일을 결합하며 output_path 경로로 output_format 형식으로 생성
    # 즉, output_path에 최종 AI 커버 곡 파일 생성(ex. Post Malone - AUSTIN (Official Live Performances) ｜ Vevo (IShowSpeed Ver))
    main_vocal_audio = AudioSegment.from_wav(audio_paths[0]) - 4 + main_gain # ai_vocals_mixed_path(AI 보컬)
    backup_vocal_audio = AudioSegment.from_wav(audio_paths[1]) - 6 + backup_gain # backup_vocals_path(백업 보컬)
    instrumental_audio = AudioSegment.from_wav(audio_paths[2]) - 7 + inst_gain # instrumentals_path(악기 음악)
    main_vocal_audio.overlay(backup_vocal_audio).overlay(instrumental_audio).export(output_path, format=output_format)


# song_input : original 파일 경로 ("디렉토리_경로/음성파일.wav"
def song_cover_pipeline(song_input, voice_model, pitch_change, keep_files,
                        is_webui=0, main_gain=0, backup_gain=0, inst_gain=0, index_rate=0.5, filter_radius=3,
                        rms_mix_rate=0.25, f0_method='rmvpe', crepe_hop_length=128, protect=0.33, pitch_change_all=0,
                        reverb_rm_size=0.15, reverb_wet=0.2, reverb_dry=0.8, reverb_damping=0.7, output_format='mp3',
                        progress=gr.Progress()):
    try:
        if not song_input or not voice_model:
            raise_exception('Ensure that the song input field and video model field is filled.', is_webui)

        display_progress('[~] Starting AI Cover Generation Pipeline...', 0, is_webui, progress)

        with open(os.path.join(mdxnet_models_dir, 'model_data.json')) as infile:
            mdx_model_params = json.load(infile)

        input_type = 'local'
        song_input = song_input.strip('\"')
        if os.path.exists(song_input):
            # local 경로로부터 song_id 추출
            song_id = get_hash(song_input)
        else:
            error_msg = f'{song_input} does not exist.'
            song_id = None
            raise_exception(error_msg, is_webui)

        # 저장 경로 설정 -> song_dir = "output_dir/song_id"
        song_dir = os.path.join(output_dir, song_id)
        os.makedirs(song_dir)

        # ================================================================================================================================================================================================================== #

        # 저장 경로에 맞게 폴더 생성 후 오디오 전처리(보컬, 백업 보컬, 악기 등 분리 -> 우리 프로젝트에선 필요 없을 것으로 예상)
        # 우리 프로젝트에선 그냥 original 음성 파일 경로인 song_input만 사용하면 됨
        # if not os.path.exists(song_dir):
        #     os.makedirs(song_dir)
        #     orig_song_path, vocals_path, instrumentals_path, main_vocals_path, backup_vocals_path, main_vocals_dereverb_path = preprocess_song(song_input, mdx_model_params, song_id, is_webui, input_type, progress)
        #     # song_output_dir = os.path.join(output_dir, song_id)
        #
        # # 이미 저장 경로가 있는 경우(이미 전처리가 수행된 경우)
        # else:
        #     vocals_path, main_vocals_path = None, None
        #     paths = get_audio_paths(song_dir)
        #     main_vocals_dereverb_path = os.path.join(song_dir, file)
        #
        #     # if any of the audio files aren't available or keep intermediate files, rerun preprocess
        #     # 경로 일부가 없거나 or 중간 파일을 보관해야 하는 경우(?) 전처리 다시 실행
        #     if any(path is None for path in paths) or keep_files:
        #         orig_song_path, vocals_path, instrumentals_path, main_vocals_path, backup_vocals_path, main_vocals_dereverb_path = preprocess_song(song_input, mdx_model_params, song_id, is_webui, input_type, progress)
        #     # 이미 전처리된 파일을 사용하는 경우 -> 이미 수행된 전처리 경로를 사용하여 결과물 설정
        #     else:
        #         orig_song_path, instrumentals_path, main_vocals_dereverb_path, backup_vocals_path = paths

        # ================================================================================================================================================================================================================== #

        # original 음악 파일 경로를 convert_to_stereo() 함수로
        orig_song_path = convert_to_stereo(song_input)

        pitch_change = pitch_change * 12 + pitch_change_all
        # AI 보컬 파일 경로
        ai_vocals_path = os.path.join(song_dir, f'{os.path.splitext(os.path.basename(orig_song_path))[0]}_{voice_model}_p{pitch_change}_i{index_rate}_fr{filter_radius}_rms{rms_mix_rate}_pro{protect}_{f0_method}{"" if f0_method != "mangio-crepe" else f"_{crepe_hop_length}"}.wav')
        # 최종 AI 커버 파일의 경로
        # ai_cover_path = os.path.join(song_dir, f'{os.path.splitext(os.path.basename(orig_song_path))[0]} ({voice_model} Ver).{output_format}')

        # 이미 만들어진 AI 보컬 파일이 없다면
        if not os.path.exists(ai_vocals_path):
            display_progress('[~] Converting video using RVC...', 0.5, is_webui, progress)
            # AI 보컬 생성 ->
            # voice_change(voice_model, main_vocals_dereverb_path, ai_vocals_path, pitch_change, f0_method, index_rate, filter_radius, rms_mix_rate, protect, crepe_hop_length, is_webui)
            voice_change(voice_model, orig_song_path, ai_vocals_path, pitch_change, f0_method, index_rate,
                         filter_radius, rms_mix_rate, protect, crepe_hop_length, is_webui)

        display_progress('[~] Applying audio effects to Vocals...', 0.8, is_webui, progress)

        # ================================================================================================================================================================================================================== #
        # AI 보컬에 오디오 효과를 적용(주로 리버브 효과 적용)
        # ai_vocals_mixed_path = add_audio_effects(ai_vocals_path, reverb_rm_size, reverb_wet, reverb_dry, reverb_damping)

        # pitch 설정값 적용
        # if pitch_change_all != 0:
        #     display_progress('[~] Applying overall pitch change', 0.85, is_webui, progress)
        #     instrumentals_path = pitch_shift(instrumentals_path, pitch_change_all)
        #     backup_vocals_path = pitch_shift(backup_vocals_path, pitch_change_all)

        # display_progress('[~] Combining AI Vocals and Instrumentals...', 0.9, is_webui, progress)
        
        # AI 보컬과 악기를 결합하여 최종 커버 곡을 생성
        # combine_audio([ai_vocals_mixed_path, backup_vocals_path, instrumentals_path], ai_cover_path, main_gain, backup_gain, inst_gain, output_format)

        # 사용자가 따로 지정하지 않으면 false로 간주
        # 처리 과정에서 나온 중간 파일들 삭제(vocals_path, main_vocals_path, ai_vocals_mixed_path, instrumentals_path, backup_vocals_path)
        # if not keep_files:
        #     display_progress('[~] Removing intermediate audio files...', 0.95, is_webui, progress)
        #     intermediate_files = [vocals_path, main_vocals_path, ai_vocals_mixed_path]
        #     if pitch_change_all != 0:
        #         intermediate_files += [instrumentals_path, backup_vocals_path]
        #     for file in intermediate_files:
        #         if file and os.path.exists(file):
        #             os.remove(file)
        # ================================================================================================================================================================================================================== #

        display_progress('변환 완료', 0.9, is_webui, progress)

        return ai_vocals_path

    except Exception as e:
        raise_exception(str(e), is_webui)


# '-k', '--keep-files' : 따로 지정하지 않으면 false로 간주
if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Generate a AI cover song in the song_output/id directory.', add_help=True)
    parser.add_argument('-i', '--song-input', type=str, required=True, help='Link to a YouTube video or the filepath to a local mp3/wav file to create an AI cover of')
    parser.add_argument('-dir', '--rvc-dirname', type=str, required=True, help='Name of the folder in the rvc_models directory containing the RVC model file and optional index file to use')
    parser.add_argument('-p', '--pitch-change', type=int, required=True, help='Change the pitch of AI Vocals only. Generally, use 1 for male to female and -1 for vice-versa. (Octaves)')
    parser.add_argument('-k', '--keep-files', action=argparse.BooleanOptionalAction, help='Whether to keep all intermediate audio files generated in the song_output/id directory, e.g. Isolated Vocals/Instrumentals')
    parser.add_argument('-ir', '--index-rate', type=float, default=0.5, help='A decimal number e.g. 0.5, used to reduce/resolve the timbre leakage problem. If set to 1, more biased towards the timbre quality of the training dataset')
    parser.add_argument('-fr', '--filter-radius', type=int, default=3, help='A number between 0 and 7. If >=3: apply median filtering to the harvested pitch results. The value represents the filter radius and can reduce breathiness.')
    parser.add_argument('-rms', '--rms-mix-rate', type=float, default=0.25, help="A decimal number e.g. 0.25. Control how much to use the original vocal's loudness (0) or a fixed loudness (1).")
    parser.add_argument('-palgo', '--pitch-detection-algo', type=str, default='rmvpe', help='Best option is rmvpe (clarity in vocals), then mangio-crepe (smoother vocals).')
    parser.add_argument('-hop', '--crepe-hop-length', type=int, default=128, help='If pitch detection algo is mangio-crepe, controls how often it checks for pitch changes in milliseconds. The higher the value, the faster the conversion and less risk of video cracks, but there is less pitch accuracy. Recommended: 128.')
    parser.add_argument('-pro', '--protect', type=float, default=0.33, help='A decimal number e.g. 0.33. Protect voiceless consonants and breath sounds to prevent artifacts such as tearing in electronic music. Set to 0.5 to disable. Decrease the value to increase protection, but it may reduce indexing accuracy.')
    parser.add_argument('-mv', '--main-vol', type=int, default=0, help='Volume change for AI main vocals in decibels. Use -3 to decrease by 3 decibels and 3 to increase by 3 decibels')
    parser.add_argument('-bv', '--backup-vol', type=int, default=0, help='Volume change for backup vocals in decibels')
    parser.add_argument('-iv', '--inst-vol', type=int, default=0, help='Volume change for instrumentals in decibels')
    parser.add_argument('-pall', '--pitch-change-all', type=int, default=0, help='Change the pitch/key of vocals and instrumentals. Changing this slightly reduces sound quality')
    parser.add_argument('-rsize', '--reverb-size', type=float, default=0.15, help='Reverb room size between 0 and 1')
    parser.add_argument('-rwet', '--reverb-wetness', type=float, default=0.2, help='Reverb wet level between 0 and 1')
    parser.add_argument('-rdry', '--reverb-dryness', type=float, default=0.8, help='Reverb dry level between 0 and 1')
    parser.add_argument('-rdamp', '--reverb-damping', type=float, default=0.7, help='Reverb damping between 0 and 1')
    parser.add_argument('-oformat', '--output-format', type=str, default='mp3', help='Output format of audio file. mp3 for smaller file size, wav for best quality')
    args = parser.parse_args()

    rvc_dirname = args.rvc_dirname
    if not os.path.exists(os.path.join(rvc_models_dir, rvc_dirname)):
        raise Exception(f'The folder {os.path.join(rvc_models_dir, rvc_dirname)} does not exist.')

    cover_path = song_cover_pipeline(args.song_input, rvc_dirname, args.pitch_change, args.keep_files,
                                     main_gain=args.main_vol, backup_gain=args.backup_vol, inst_gain=args.inst_vol,
                                     index_rate=args.index_rate, filter_radius=args.filter_radius,
                                     rms_mix_rate=args.rms_mix_rate, f0_method=args.pitch_detection_algo,
                                     crepe_hop_length=args.crepe_hop_length, protect=args.protect,
                                     pitch_change_all=args.pitch_change_all,
                                     reverb_rm_size=args.reverb_size, reverb_wet=args.reverb_wetness,
                                     reverb_dry=args.reverb_dryness, reverb_damping=args.reverb_damping,
                                     output_format=args.output_format)
    print(f'[+] Cover generated at {cover_path}')
