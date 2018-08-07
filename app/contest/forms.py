from flask_wtf import FlaskForm
from wtforms import SubmitField, SelectField, HiddenField, BooleanField


class SubmitProblemForm(FlaskForm):
    contest_id = HiddenField('Contest')
    problem_id = HiddenField('Problem')
    language = SelectField('Language')
    source_code = HiddenField('Source code')
    share = BooleanField('Share your code with others')
    submit = SubmitField('Submit')

    def __init__(self, language=None, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.language.choices = language or []
