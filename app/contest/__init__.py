from flask import Blueprint

contest = Blueprint('contest', __name__)

from . import views
