from flask import Flask
from flask import render_template, url_for, request, flash, redirect
from typing import List
from sqlalchemy.orm import DeclarativeBase, mapped_column, relationship, Mapped, Session
from sqlalchemy import String, ForeignKey, create_engine, select, update,LargeBinary
from flask_wtf import Form
from wtforms import StringField, EmailField, SubmitField
from wtforms.validators import DataRequired, EqualTo
from flask_bootstrap import Bootstrap
from werkzeug.security import generate_password_hash, check_password_hash
from flask_login import LoginManager, UserMixin, login_user, current_user, login_required, logout_user
# GEMINI CODE
import google.generativeai as genai
from constants import get_seed_prompt
import os
from dotenv import load_dotenv

import pickle


load_dotenv()


GEMINI_KEY = os.getenv('GEMINI_KEY')
SECRET_KEY = os.getenv('SECRET_KEY')



# GEMINI CODE
genai.configure(api_key=GEMINI_KEY)


"""
Seed prompt = 

You are baymax from big hero 6 and talking to client like a robo-human and trying as an assistant to uplift their mood and make them happy and laugh and listen to them.

Do not use default messages for prohibited prompts.

The client's name is {name}
and do not exceed 50 words during replies.
Greet them with a warm manner and with a joke as the first reply to hi
"""


model = genai.GenerativeModel("gemini-1.5-flash", safety_settings=[
      {
        "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
        "threshold": "BLOCK_NONE"
      },
      {
        "category": "HARM_CATEGORY_HATE_SPEECH",
        "threshold": "BLOCK_NONE"
      },
      {
        "category": "HARM_CATEGORY_HARASSMENT",
        "threshold": "BLOCK_NONE"
      },
      {
        "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
        "threshold": "BLOCK_NONE"
        }])




#sqlite engine
# engine = create_engine("sqlite:///static/data/database/data.db", echo=True)  
URL = os.getenv('POSTGRES_URL').replace('postgres://', 'postgresql://')
print(URL)
engine = create_engine(url=URL, echo=True)



#flask dependencies
app = Flask(__name__)
app.secret_key = SECRET_KEY
bootstrap = Bootstrap(app)


#flask-login instantiation
login_manager = LoginManager() 
login_manager.init_app(app)

#pkl file system
folder_path = "tmp\\pkl_files"

class Base(DeclarativeBase):
    pass


#Table ORM Classes
class User(Base):
    __tablename__ = "user_account"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(30))
    email: Mapped[str] = mapped_column(String(30))
    pswd_hash: Mapped[str] = mapped_column(String())
    conversations: Mapped[LargeBinary] = mapped_column(LargeBinary())




Base.metadata.create_all(engine) #create tables


# WTF-FORMS
class RegisterForm(Form):
    name = StringField("name", validators=[DataRequired("Name Required")])
    email = EmailField("email", validators=[DataRequired("Email Required")])
    pswd = StringField("password", validators=[DataRequired("Password Required")])
    confirm_pswd = StringField("cnf_password", validators=[DataRequired(''), EqualTo('pswd', message="Passwords must match.")])
    submit = SubmitField("submit")


class LoginForm(Form):
    email = EmailField("email", validators=[DataRequired("Email Required")])
    pswd = StringField("password", validators=[DataRequired("Password Required")])
    submit = SubmitField("submit")
    
    


#flask-login dependency
class Client(UserMixin):
    def __init__(self, user_id) -> None:
        self.id = user_id



@login_manager.user_loader
def load_user(user_id):
    with Session(engine) as session:
        stmt = select(User).where(User.id == user_id)
        data = session.scalar(stmt)
        user_obj = Client(user_id)
        user_obj.name = data.name

    return user_obj




@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login", methods=["POST", "GET"])
def login():
    form : LoginForm = LoginForm(request.form)
    if current_user.is_authenticated:
        return redirect("choose")
    
    if request.method == "POST":
        if form.validate():
            stmt = select(User).where(User.email == form.email.data)
            with Session(engine) as session:
                response = session.scalar(stmt)
                if response:
                    user_data = response
                    if check_password_hash(user_data.pswd_hash, form.pswd.data):
                        login_user(Client(user_data.id))
                        return redirect('choose')
                    else:
                        flash('Incorrect password', category='error')

                else:
                    flash('Incorrect Email', category='error')

            
    return render_template("login.html", form=form)

@app.route("/register", methods=["GET", "POST"])
def register():

    form: RegisterForm = RegisterForm(request.form)    
    if request.method == "POST":
        if form.validate():    
            with Session(engine) as session:
                stmt = select(User).where(User.email == form.email.data)
                response = session.scalar(stmt)
                if response:
                    flash("Email already exists")
                    return redirect('register')
                else:

                    new_user = User(name=form.name.data, email=form.email.data, pswd_hash=generate_password_hash(form.pswd.data), conversations=pickle.dumps([]))
                    session.add(new_user)
                    session.commit()
                    return redirect('login')
           
    return render_template("register.html", form=form)

@app.route("/choose")
@login_required
def choose():
    return render_template('choice_page.html')





@app.route("/chatbox", methods=["GET", "POST"])
@login_required
def chatbox():
    global history
    global session_processes

    file_name = f'{folder_path}\\{current_user.id}.pkl'

    conv = []
    with Session(engine) as session:
        stmt = select(User).where(User.id == current_user.id)
        response = session.scalar(stmt)
        conv = pickle.loads(response.conversations)


    if conv:
        chat = model.start_chat(history=conv)

    else:
        SEED_PROMPT = get_seed_prompt(current_user.name)
        chat = model.start_chat(history=conv)
        chat.send_message(SEED_PROMPT)
        
    


    
    if request.method == "POST":
        msg = request.form.get('msg')
        if msg == "clear":
            chat.history = []
            with Session(engine) as session:
                stmt = select(User).where(User.id == current_user.id)
                user_obj = session.scalar(stmt)
                user_obj.conversations = pickle.dumps([])
                session.commit()

            return redirect('chatbox')
        
        elif msg:
            chat.send_message(msg)
            with Session(engine) as session:
                stmt = select(User).where(User.id == current_user.id)
                user_obj = session.scalar(stmt)
                conv = chat.history
                conv_serialised = pickle.dumps(conv)
                user_obj.conversations = conv_serialised
                session.commit()


            return redirect('chatbox')
        

    
    return render_template('chatbox.html', history=chat.history[1:])

@app.route("/logout")
@login_required
def logout():
  
    logout_user()
    return redirect('/')


if __name__ == "__main__":
    app.run(debug=True)