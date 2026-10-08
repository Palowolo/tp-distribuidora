import os
from pathlib import Path
from uuid import uuid4
from flask import Flask, render_template, send_from_directory
from flask_wtf.csrf import CSRFProtect, CSRFError
from dotenv import load_dotenv
import psycopg
from .validation import gs, BusinessError

def create_app(config=None):
    load_dotenv()
    app = Flask(__name__, static_folder=None)
    app.config.update(SECRET_KEY=os.environ.get('SECRET_KEY'),
        SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax',
        SESSION_COOKIE_SECURE=os.environ.get('APP_ENV') in ('preview','production'),
        MAX_CONTENT_LENGTH=128*1024, WTF_CSRF_TIME_LIMIT=3600)
    if config: app.config.update(config)
    CSRFProtect(app)
    app.jinja_env.filters['gs'] = gs
    app.jinja_env.globals['new_token'] = lambda: str(uuid4())
    from .routes import catalog, orders, reports
    for blueprint in (catalog, orders, reports): app.register_blueprint(blueprint)

    @app.get('/static/<path:filename>')
    def assets(filename):
        return send_from_directory(Path(app.root_path).parent/'public'/'static', filename)

    @app.get('/health')
    def health(): return {'status':'ok'}

    @app.errorhandler(BusinessError)
    def business_error(error): return render_template('error.html',message=str(error)), 422

    @app.errorhandler(CSRFError)
    def csrf_error(error): return render_template('error.html',message='El formulario venció o no es válido. Recargá la página antes de volver a enviar.'), 400

    @app.errorhandler(psycopg.IntegrityError)
    def conflict(error): return render_template('error.html',message='Los datos no cumplen las restricciones. Verificá el código único y las cantidades.'), 409

    @app.errorhandler(psycopg.Error)
    def db_error(error):
        app.logger.error('Error de base de datos: %s',type(error).__name__)
        return render_template('error.html',message='No pudimos completar la operación. Intentá nuevamente en unos momentos.'), 503

    @app.errorhandler(404)
    def missing(error): return render_template('error.html',message='No se encontró la página o el registro.'), 404

    @app.errorhandler(500)
    def unexpected(error): return render_template('error.html',message='No pudimos completar la operación.'), 500

    @app.after_request
    def headers(response):
        response.headers['X-Content-Type-Options']='nosniff'
        response.headers['X-Frame-Options']='DENY'
        response.headers['Referrer-Policy']='same-origin'
        response.headers['Content-Security-Policy']="default-src 'self'; style-src 'self' https://cdn.jsdelivr.net; script-src 'self'; img-src 'self' data:; font-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
        if not __import__('flask').request.path.startswith('/static/'):
            response.headers['Cache-Control']='no-store'
        return response
    return app
