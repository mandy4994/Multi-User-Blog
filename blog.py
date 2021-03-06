import os
import re
import random
import hashlib
import time
import hmac
import logging
from string import letters

import webapp2
import jinja2

from google.appengine.ext import db

template_dir = os.path.join(os.path.dirname(__file__), 'templates')
jinja_env = jinja2.Environment(loader=jinja2.FileSystemLoader(template_dir),
                               autoescape=True)

secret = 'fart'


def render_str(template, **params):
    t = jinja_env.get_template(template)
    return t.render(params)


def make_secure_val(val):
    return '%s|%s' % (val, hmac.new(secret, val).hexdigest())


def check_secure_val(secure_val):
    val = secure_val.split('|')[0]
    if secure_val == make_secure_val(val):
        return val


class BlogHandler(webapp2.RequestHandler):

    def write(self, *a, **kw):
        self.response.out.write(*a, **kw)

    def render_str(self, template, **params):
        params['user'] = self.user
        return render_str(template, **params)

    def render(self, template, **kw):
        self.write(self.render_str(template, **kw))

    def set_secure_cookie(self, name, val):
        cookie_val = make_secure_val(val)
        self.response.headers.add_header(
            'Set-Cookie',
            '%s=%s; Path=/' % (name, cookie_val))

    def read_secure_cookie(self, name):
        cookie_val = self.request.cookies.get(name)
        return cookie_val and check_secure_val(cookie_val)

    def login(self, user):
        self.set_secure_cookie('user_id', str(user.key().id()))

    def logout(self):
        self.response.headers.add_header('Set-Cookie', 'user_id=; Path=/')

    def initialize(self, *a, **kw):
        webapp2.RequestHandler.initialize(self, *a, **kw)
        uid = self.read_secure_cookie('user_id')
        self.user = uid and User.by_id(int(uid))


def render_post(response, post):
    response.out.write('<b>' + post.subject + '</b><br>')
    response.out.write(post.content)


class MainPage(BlogHandler):

    def get(self):
        self.write('Hello, Udacity!')


# user stuff
def make_salt(length=5):
    return ''.join(random.choice(letters) for x in xrange(length))


def make_pw_hash(name, pw, salt=None):
    if not salt:
        salt = make_salt()
    h = hashlib.sha256(name + pw + salt).hexdigest()
    return '%s,%s' % (salt, h)


def valid_pw(name, password, h):
    salt = h.split(',')[0]
    return h == make_pw_hash(name, password, salt)


def users_key(group='default'):
    return db.Key.from_path('users', group)


class User(db.Model):
    name = db.StringProperty(required=True)
    pw_hash = db.StringProperty(required=True)
    email = db.StringProperty()

    @classmethod
    def by_id(cls, uid):
        return User.get_by_id(uid, parent=users_key())

    @classmethod
    def by_name(cls, name):
        u = User.all().filter('name =', name).get()
        return u

    @classmethod
    def register(cls, name, pw, email=None):
        pw_hash = make_pw_hash(name, pw)
        return User(parent=users_key(),
                    name=name,
                    pw_hash=pw_hash,
                    email=email)

    @classmethod
    def login(cls, name, pw):
        u = cls.by_name(name)
        if u and valid_pw(name, pw, u.pw_hash):
            return u


# blog stuff

def blog_key(name='default'):
    return db.Key.from_path('blogs', name)


class UserCommentPosts(db.Model):
    username = db.StringProperty(required=True)
    post_id = db.IntegerProperty(required=True)
    comment = db.StringProperty(required=True)


class UserLikedPost(db.Model):
    userid = db.StringProperty(required=True)
    post_id = db.IntegerProperty(required=True)


class Post(db.Model):
    userid = db.StringProperty(required=False)
    subject = db.StringProperty(required=True)
    content = db.TextProperty(required=True)
    created = db.DateTimeProperty(auto_now_add=True)
    last_modified = db.DateTimeProperty(auto_now=True)
    likes = db.IntegerProperty(required=False)

    def render(self):
        self._render_text = self.content.replace('\n', '<br>')
        return render_str("post.html", p=self)


class BlogFront(BlogHandler):

    def get(self):
        posts = greetings = Post.all().order('-created')
        comments = UserCommentPosts.all()
        self.render('front.html', posts=posts, comments=comments)


class PostPage(BlogHandler):

    def get(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)

        if not post:
            self.error(404)
            return

        self.render("permalink.html", post=post)


class NewPost(BlogHandler):

    def get(self):
        if self.user:
            self.render("newpost.html")
        else:
            self.redirect("/login")

    def post(self):
        if not self.user:
            return
        self.redirect('/login')

        subject = self.request.get('subject')
        content = self.request.get('content')

        if subject and content:
            p = Post(parent=blog_key(), userid=self.read_secure_cookie(
                'user_id'), subject=subject, content=content, likes=0)
            p.put()
            self.redirect('/blog/%s' % str(p.key().id()))
        else:
            error = "subject and content, please!"
            self.render(
                "newpost.html", subject=subject, content=content, error=error)

# Handler for editing post


class EditPost(BlogHandler):

    def get(self, post_id):
        # Check if user editing is the one who posted
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)
        if self.user and self.read_secure_cookie('user_id') == post.userid:
            self.render(
                "newpost.html", subject=post.subject, content=post.content)
        else:
            self.redirect("/login")

    def post(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)
        if self.user and self.read_secure_cookie('user_id') == post.userid:
            subject = self.request.get('subject')
            content = self.request.get('content')

            if subject and content:
                key = db.Key.from_path('Post', int(post_id), parent=blog_key())
                post = db.get(key)
                # change the post's data
                post.subject = subject
                post.content = content
                # Update in database
                post.put()
                self.redirect('/blog/%s' % str(post.key().id()))
            else:
                error = "subject and content, please!"
                self.render("newpost.html",
                            subject=subject, content=content, error=error)
        else:
            self.redirect("/login")

# Handler for deleting post


class DeletePost(BlogHandler):

    def get(self, post_id):
        key = db.Key.from_path('Post', int(post_id), parent=blog_key())
        post = db.get(key)
        # Check if current user is the author of the post
        if self.user and self.read_secure_cookie('user_id') == post.userid:
            post.delete()
            time.sleep(1)
            self.redirect("/blog")
        else:
            self.redirect("/login")

# Handler for liking post


class LikePost(BlogHandler):

    def get(self, post_id):
        # Check if user is logged in to like post
        if self.user:
            key = db.Key.from_path('Post', int(post_id), parent=blog_key())
            post = db.get(key)
            userid = self.read_secure_cookie('user_id')
            comments = UserCommentPosts.all()
            # Check if author is not liking his own post
            if userid != post.userid:
                # check if user has liked the post before
                query = db.GqlQuery(
                    "SELECT * FROM UserLikedPost WHERE \
                     userid = '" + userid + "' and post_id =" + post_id)
                count = query.count()
                if count > 0:
                    error = "You already liked this post"
                    posts = greetings = Post.all().order('-created')
                    self.render('front.html', comments=comments,
                                posts=posts, error=error)

                else:
                    post.likes = post.likes + 1
                    post.put()
                    lp = UserLikedPost(userid=userid, post_id=int(post_id))
                    lp.put()

                    time.sleep(2)
                    self.redirect("/blog")
            else:
                error = "You can't like your own post"
                posts = greetings = Post.all().order('-created')
                self.render(
                    'front.html', comments=comments, posts=posts, error=error)

        else:
            self.redirect("/login")

# Handler for commenting on post


class CommentPost(BlogHandler):

    def post(self):
        # if user is not logged in he is redirected to login screen
        if not self.user:
            self.redirect('/login')
        else:
            userid = self.read_secure_cookie('user_id')
            comment = self.request.get('comment')
            post_id = self.request.get('post_id')
            posts = greetings = Post.all().order('-created')
            comments = UserCommentPosts.all()

            if comment:
                user = User.by_id(int(userid))
                username = user.name
                # enter to database
                cp = UserCommentPosts(
                    username=username, post_id=int(post_id), comment=comment)
                cp.put()
                time.sleep(1)
                comments = UserCommentPosts.all()
                self.render('front.html', posts=posts, comments=comments)

            else:
                error = "Comment can't be empty"
                self.render(
                    'front.html', comments=comments, posts=posts, error=error)

# Handler for editing comment on post


class EditComment(BlogHandler):

    def post(self, commentid):
        if self.user:
            logging.info(commentid)
            # get comment object from comment id
            key = db.Key.from_path('UserCommentPosts', int(commentid))
            comment = db.get(key)
            userid = self.read_secure_cookie('user_id')
            user = User.by_id(int(userid))
            newcomment = self.request.get('editedcomment')
            # compare if user logged in is the one who commented by checking
            # username since every username is unique
            if user.name == comment.username:
                comment.comment = newcomment
                comment.put()
                posts = greetings = Post.all().order('-created')
                comments = UserCommentPosts.all()
                time.sleep(1)
                self.render('front.html', posts=posts, comments=comments)
            else:
                error = "You can only edit your comment"
                posts = greetings = Post.all().order('-created')
                comments = UserCommentPosts.all()
                self.render(
                    'front.html', posts=posts, comments=comments, error=error)
        else:
            self.redirect("/login")

# Handler for deleting comment on post


class DeleteComment(BlogHandler):

    def get(self):
        if self.user:
            commentid = self.request.get("commentid")
            key = db.Key.from_path('UserCommentPosts', int(commentid))
            comment = db.get(key)
            userid = self.read_secure_cookie('user_id')
            user = User.by_id(int(userid))
            # compare if user logged in is the one who commented by checking
            # username since every username is unique
            if user.name == comment.username:
                comment.delete()
                time.sleep(1)
                self.redirect("/blog")
            else:
                error = "You can only delete your comment"
                posts = greetings = Post.all().order('-created')
                comments = UserCommentPosts.all()
                self.render(
                    'front.html', posts=posts, comments=comments, error=error)

        else:
            self.redirect("/login")

# Unit 2 HW's


class Rot13(BlogHandler):

    def get(self):
        self.render('rot13-form.html')

    def post(self):
        rot13 = ''
        text = self.request.get('text')
        if text:
            rot13 = text.encode('rot13')

        self.render('rot13-form.html', text=rot13)


USER_RE = re.compile(r"^[a-zA-Z0-9_-]{3,20}$")


def valid_username(username):
    return username and USER_RE.match(username)

PASS_RE = re.compile(r"^.{3,20}$")


def valid_password(password):
    return password and PASS_RE.match(password)

EMAIL_RE = re.compile(r'^[\S]+@[\S]+\.[\S]+$')


def valid_email(email):
    return not email or EMAIL_RE.match(email)


class Signup(BlogHandler):

    def get(self):
        self.render("signup-form.html")

    def post(self):
        have_error = False
        self.username = self.request.get('username')
        self.password = self.request.get('password')
        self.verify = self.request.get('verify')
        self.email = self.request.get('email')

        params = dict(username=self.username,
                      email=self.email)

        if not valid_username(self.username):
            params['error_username'] = "That's not a valid username."
            have_error = True

        if not valid_password(self.password):
            params['error_password'] = "That wasn't a valid password."
            have_error = True
        elif self.password != self.verify:
            params['error_verify'] = "Your passwords didn't match."
            have_error = True

        if not valid_email(self.email):
            params['error_email'] = "That's not a valid email."
            have_error = True

        if have_error:
            self.render('signup-form.html', **params)
        else:
            self.done()

    def done(self, *a, **kw):
        raise NotImplementedError


class Unit2Signup(Signup):

    def done(self):
        self.redirect('/unit2/welcome?username=' + self.username)


class Register(Signup):

    def done(self):
        # make sure the user doesn't already exist
        u = User.by_name(self.username)
        if u:
            msg = 'That user already exists.'
            self.render('signup-form.html', error_username=msg)
        else:
            u = User.register(self.username, self.password, self.email)
            u.put()

            self.login(u)
            self.redirect('/blog')


class Login(BlogHandler):

    def get(self):
        self.render('login-form.html')

    def post(self):
        username = self.request.get('username')
        password = self.request.get('password')

        u = User.login(username, password)
        if u:
            self.login(u)
            self.redirect('/blog')
        else:
            msg = 'Invalid login'
            self.render('login-form.html', error=msg)


class Logout(BlogHandler):

    def get(self):
        self.logout()
        self.redirect('/login')


class Unit3Welcome(BlogHandler):

    def get(self):
        if self.user:
            self.render('welcome.html', username=self.user.name)
        else:
            self.redirect('/signup')


class Welcome(BlogHandler):

    def get(self):
        username = self.request.get('username')
        if valid_username(username):
            self.render('welcome.html', username=username)
        else:
            self.redirect('/unit2/signup')

app = webapp2.WSGIApplication([('/', MainPage),
                               ('/unit2/rot13', Rot13),
                               ('/unit2/signup', Unit2Signup),
                               ('/unit2/welcome', Welcome),
                               ('/blog/?', BlogFront),
                               ('/blog/([0-9]+)', PostPage),
                               ('/blog/newpost', NewPost),
                               ('/signup', Register),
                               ('/login', Login),
                               ('/logout', Logout),
                               ('/unit3/welcome', Unit3Welcome),
                               ('/blog/edit/([0-9]+)', EditPost),
                               ('/blog/delete/([0-9]+)', DeletePost),
                               ('/blog/like/([0-9]+)', LikePost),
                               ('/blog/comment', CommentPost),
                               ('/blog/editcomment/([0-9a-zA-Z]+)',
                                EditComment),
                               ('/blog/deletecomment', DeleteComment)
                               ],
                              debug=True)
