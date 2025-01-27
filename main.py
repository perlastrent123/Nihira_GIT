import email_validator
import os
import sqlalchemy.exc
from datetime import date
from flask import Flask, abort, render_template, redirect, url_for, flash, session, g
from flask_bootstrap import Bootstrap5
from flask_ckeditor import CKEditor
from flask_gravatar import Gravatar
from flask_login import UserMixin, login_user, LoginManager, current_user, logout_user
from flask_sqlalchemy import SQLAlchemy
from forms import CreatePostForm, RegisterForm, LoginForm, CommentForm
from functools import wraps
from werkzeug.security import generate_password_hash, check_password_hash
from sqlalchemy.orm import relationship

app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('FLASK_KEY')
ckeditor = CKEditor(app)
Bootstrap5(app)

login_manager = LoginManager()
login_manager.init_app(app)

gravatar = Gravatar(app,
                    size=100,
                    rating='g',
                    default='retro',
                    force_default=False,
                    force_lower=False,
                    use_ssl=False,
                    base_url=None)

# CONNECT TO DB
app.config['SQLALCHEMY_DATABASE_URI'] = "sqlite:///blog.db"
# app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get("DB_URI", "sqlite:///blog.db")
db = SQLAlchemy()
db.init_app(app)


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(100), unique=True)
    password = db.Column(db.String(100))
    name = db.Column(db.String(1000))
    posts = db.relationship('BlogPost', backref='user')


class BlogPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    title = db.Column(db.String(250), unique=True, nullable=False)
    subtitle = db.Column(db.String(250), nullable=False)
    date = db.Column(db.String(250), nullable=False)
    body = db.Column(db.Text, nullable=False)
    author = db.Column(db.String(250), nullable=False)
    img_url = db.Column(db.String(250), nullable=False)


class Comment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    text = db.Column(db.String(250), nullable=False)
    author = db.relationship('User', backref='author')
    parent_post_id = db.Column(db.Integer, db.ForeignKey('blog_post.id'))


with app.app_context():
    db.create_all()


def admin_only(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if session['user_id'] != 1:
            return abort(403)
        return f(*args, **kwargs)

    return wrapper


@app.route('/register', methods=['POST', 'GET'])
def register():
    form = RegisterForm()
    if current_user.is_authenticated:
        return redirect(url_for('get_all_posts'))
    if form.validate_on_submit():
        try:
            user_name = form.name.data
            user_pass = form.password.data
            hashed_pass = generate_password_hash(user_pass, method='pbkdf2:sha256', salt_length=8)
            new_user = User(
                name=user_name,
                password=hashed_pass,
                email=form.email.data
            )
            db.session.add(new_user)
            db.session.commit()
            login_user(new_user)
            session['username'] = new_user.name
            session['user_id'] = new_user.id
            return redirect(url_for('get_all_posts'))
        except sqlalchemy.exc.IntegrityError:
            flash('Email already exists. Please login instead.', 'error')
            return redirect(url_for('login'))
    return render_template("register.html", form=form)


@app.route('/login', methods=['POST', 'GET'])
def login():
    form = LoginForm()
    if current_user.is_authenticated:
        return redirect(url_for('get_all_posts'))
    if form.validate_on_submit():
        user_email = form.email.data
        user_pass = form.password.data
        user = User.query.filter_by(email=user_email).first()
        if user and check_password_hash(user.password, user_pass):
            login_user(user)
            session['username'] = user.name
            session['user_id'] = user.id
            return redirect(url_for('get_all_posts'))
        else:
            flash('Invalid Credentials', 'error')
    return render_template("login.html", form=form)


@app.route('/logout')
def logout():
    [session.pop(key) for key in list(session.keys()) if not key.startswith('_')]
    logout_user()
    return redirect(url_for('login'))


@app.route('/')
def get_all_posts():
    if not current_user.is_authenticated:
        [session.pop(key) for key in list(session.keys()) if not key.startswith('_')]
    result = db.session.execute(db.select(BlogPost))
    posts = result.scalars().all()
    return render_template("index.html", all_posts=posts)


@app.route("/post/<int:post_id>", methods=["GET", "POST"])
def show_post(post_id):
    requested_post = db.get_or_404(BlogPost, post_id)
    comment_form = CommentForm()
    comments = db.session.execute(db.select(Comment).order_by(Comment.id)).scalars()
    if comment_form.validate_on_submit():
        if current_user.is_authenticated:
            user = db.session.execute(db.select(User).filter_by(name=session['username'])).scalar()
            blog = db.session.execute(db.select(BlogPost).filter_by(id=post_id)).scalar()
            new_comment = Comment(
                author_id=user.id,
                text=comment_form.comment.data,
                parent_post_id=blog.id,
            )
            db.session.add(new_comment)
            db.session.commit()
            return redirect(url_for('show_post', post_id=post_id))
        else:
            flash('Please login first to comment!', 'error')
            return redirect(url_for('login'))
    return render_template("post.html", post=requested_post, form=comment_form, comments=comments, post_id=post_id)


@app.route("/new-post", methods=["GET", "POST"])
@admin_only
def add_new_post():
    form = CreatePostForm()
    user = db.session.execute(db.select(User).filter_by(name=session['username'])).scalar()
    if form.validate_on_submit():
        new_post = BlogPost(
            author_id=user.id,
            title=form.title.data,
            subtitle=form.subtitle.data,
            body=form.body.data,
            img_url=form.img_url.data,
            author=session['username'],
            date=date.today().strftime("%B %d, %Y")
        )
        db.session.add(new_post)
        db.session.commit()
        return redirect(url_for("get_all_posts"))
    return render_template("make-post.html", form=form)


@app.route("/edit-post/<int:post_id>", methods=["GET", "POST"])
@admin_only
def edit_post(post_id):
    post = db.get_or_404(BlogPost, post_id)
    edit_form = CreatePostForm(
        title=post.title,
        subtitle=post.subtitle,
        img_url=post.img_url,
        author=post.author,
        body=post.body
    )
    if edit_form.validate_on_submit():
        post.title = edit_form.title.data
        post.subtitle = edit_form.subtitle.data
        post.img_url = edit_form.img_url.data
        post.author = post.author
        post.body = edit_form.body.data
        db.session.commit()
        return redirect(url_for("show_post", post_id=post.id))
    return render_template("make-post.html", form=edit_form, is_edit=True)


@app.route("/delete/<int:post_id>")
@admin_only
def delete_post(post_id):
    post_to_delete = db.get_or_404(BlogPost, post_id)
    db.session.delete(post_to_delete)
    db.session.commit()
    return redirect(url_for('get_all_posts'))


@app.route("/about")
def about():
    return render_template("about.html")


@app.route("/contact")
def contact():
    return render_template("contact.html")


@login_manager.user_loader
def load_user(user_id):
    return db.get_or_404(User, user_id)


if __name__ == "__main__":
    app.run(debug=False, port=5002)
