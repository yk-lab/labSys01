#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import re
import bottle
from bottle import TEMPLATE_PATH, static_file, jinja2_view, request
import yaml
import bibtexparser
import markdown
import firebase_admin
import firebase_admin.auth
from firebase_admin import credentials
import uuid
from pymongo import MongoClient
import datetime


app = bottle.Bottle()
TEMPLATE_PATH[:] = ['templates/html']
bottle.debug(os.getenv('debug_mode', False))
app.config['TEMPLATES_AUTO_RELOAD'] = os.getenv('debug_mode', False)

config = {
  "file_path": os.getenv('app_config', 'config.yml'),
  "apiKey": os.environ.get('firebase_apiKey'),
  "authDomain": os.environ.get('firebase_authDomain'),
  "databaseURL": os.environ.get('firebase_databaseURL'),
  "storageBucket": os.environ.get('firebase_storageBucket')
}

if os.path.isfile(config["file_path"]):
    with open(config["file_path"], 'r') as f:
        option = yaml.load(f)

client = MongoClient(os.environ.get('mongo_url'), int(os.environ.get('mongo_port')))
db = client[os.environ.get('mongo_db')]

cred = credentials.Certificate("firebase-adminsdk.json")
firebase_admin.initialize_app(cred)

@app.route("/")
@jinja2_view('index.html')
def index():
    recently_list = db['bib'].find({'slide_published_date': {'$lte': datetime.date.today().isoformat()}}).sort('slide_published_date', -1).limit(15)
    bib_list = db['bib'].find().sort('_id', -1).limit(15)
    return {'bib_list': bib_list, 'recently_list': recently_list}

@app.route("/journals/<name>/<year>/")
@app.route("/journals/<name>/")
@jinja2_view('list.html')
def journal(name, year=None):
    if (year == None):
        bib_list = db['bib'].find({'bib_data.0.journal': name}).sort('bib_data.0.year', -1)
        list_title = name
    else:
        bib_list = db['bib'].find({'bib_data.0.journal': name, 'bib_data.0.year': year}).sort('_id', -1)
        list_title = "%s (%s年)" % (name, year)
    return {'bib_list': bib_list, 'list_title': list_title}

@app.route("/date/<date>/")
@jinja2_view('list.html')
def journal(date):
    bib_list = db['bib'].find({'slide_published_date': date}).sort('_id', -1)
    list_title = "発表: %s" % (date)
    return {'bib_list': bib_list, 'list_title': list_title}

@app.route("/journals/")
@jinja2_view('tag_list.html')
def journal_list():
    bib_list = db['bib'].distinct('bib_data.0.journal', {})
    return {'tag_list': bib_list, 'page_title': 'Journal List', 'tag_type': 'journals'}

@app.route("/date/")
@jinja2_view('tag_list.html')
def journal_list():
    bib_list = db['bib'].distinct('slide_published_date', {})
    return {'tag_list': bib_list, 'page_title': 'Date', 'tag_type': 'date'}

@app.route('/static/<file_path:path>')
def static(file_path):
    return static_file(file_path, root='./static')

@app.route('/pdf/<file_path:path>')
def pdf(file_path):
    return static_file(file_path, root='/files')

@app.route('/pdf-dl/<file_path:path>')
def pdf_dl(file_path):
    return static_file(file_path, root='/files', download=True)

@app.route("/login/")
@jinja2_view('login.html')
def login():
    return {}

@app.route("/register/")
@jinja2_view('register.html')
def register():
    return {}

@app.route("/upload/", method='GET')
@jinja2_view('upload_get.html')
def get_upload():
    return {}

@app.route("/info/<id>", method='GET')
def get_upload(id):
    return {}

@app.route("/upload/", method='POST')
@jinja2_view('upload_post.html')
def post_upload():
    user = firebase_admin.auth.verify_id_token(request.forms.get('acc_key'))
    if not user['uid']:
        return 'Error!'

    pdf_file = request.files.get('pdf_file', '')
    bib_file = request.files.get('bib_file', None)
    src_file = request.files.get('source_file', '')
    if not pdf_file.filename.lower().endswith(('.pdf')) or not src_file.filename.lower().endswith(('.pdf')):
        return 'File extension not allowed!'

    if bib_file != None and not bib_file.filename.lower().endswith(('.bib')):
        return 'File extension not allowed!'


    if bib_file != None:
        bib_database = bibtexparser.loads(bib_file.file.getvalue().decode())
    elif request.forms.get('bib-name') and request.forms.get('bib-author') and request.forms.get('bib-paper') and request.forms.get('bib-year'):
        bib = {
            "name": request.forms.get('bib-name'),
            "author": request.forms.get('bib-author'),
            "paper": request.forms.get('bib-author'),
            "year": request.forms.get('bib-year')
        }
        bib_database = bibtexparser.loads(
            '@article{\n'
            '  paper1,\n'
            '  title={' + bib['name'] + '},\n'
            '  author={' + bib['author'] + '},\n'
            '  journal={' + bib['paper'] + '},\n'
            '  year={' + bib['year'] + '},\n'
            '}'
        )
    else:
        return 'Not Found Paper Info!'

    pdf_filename = uuid.uuid4().hex
    src_filename = uuid.uuid4().hex
    pdf_file.save(os.path.join(os.environ.get('file_save_path'), '%s.pdf' % pdf_filename))
    src_file.save(os.path.join(os.environ.get('file_save_path'), '%s.pdf' % src_filename))
    bib_save(pdf_filename, src_filename, user['uid'], request.forms.get('published'), bib_database)
    return {}

def bib_save(id, src, uid, slide_published_date, bib_database):
    db['bib'].update(
            {'id': id},
            {"$set": {'bib_data': bib_database.entries, 'src': src, 'uid': uid, 'id': id, 'slide_published_date': slide_published_date}},
            upsert = True
        )

if (os.getenv('APP_MODE', 'DEVELOPMENT').upper() in {'DEVELOPMENT', 'DEV'}):
    app.run(host=os.environ.get('app_hostname'), port=os.environ.get('app_port'), reloader=os.getenv('app_reloader', False))
else:
    app.run(server='paste', host=os.environ.get('app_hostname'), port=os.environ.get('app_port'))
