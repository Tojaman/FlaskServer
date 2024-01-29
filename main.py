from flask import Flask, request, render_template
app = Flask(__name__)

@app.route('/')
def hello():
    return 'Hello, World!'

@app.route('/hello/<name>')
def hellohtml(name):
    return "hello {}".format(name)
    # return render_template("hello.html")

@app.route('/method', methods=['GET', 'POST'])
def method():
    if request.method == 'GET':
        num = request.args["num"]
        name = request.args.get("name")
        return "GET으로 전달"
    else:
        num = request.form["num"]
        name = request.form["name"]
        return "POST로 전달"

if __name__ == '__main__':
    app.run(debug=True)