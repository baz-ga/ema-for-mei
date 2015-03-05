import requests
from urllib import unquote

from flask.ext.api import FlaskAPI
from flask.ext.api import status
from werkzeug.routing import BaseConverter
from flask import send_file

from omas import meiinfo
from omas import meislicer
from omas.exceptions import CannotReadMEIException
from omas.exceptions import BadApiRequest
from omas.exceptions import CannotWriteMEIException
from omas.exceptions import CannotAccessRemoteMEIException
from omas.exceptions import UnknownMEIReadException
from omas.exceptions import UnsupportedEncoding


app = FlaskAPI(__name__)

app.config['DEFAULT_RENDERERS'] = [
    'flask.ext.api.renderers.JSONRenderer',
    'flask.ext.api.renderers.BrowsableAPIRenderer',
]

app.config['DEFAULT_PARSERS'] = [
    'flask.ext.api.parsers.JSONParser',
]


# CONVERTERS
class OneOrRangeConverter(BaseConverter):

    def __init__(self, url_map):
        super(OneOrRangeConverter, self).__init__(url_map)
        self.regex = '(?:(\d+|start)(-(\d+|end))?)'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value


class OneOrMixedConverter(BaseConverter):

    def __init__(self, url_map):
        super(OneOrMixedConverter, self).__init__(url_map)
        self.regex = '(?:(\d+|start)([-,](\d+|end))*)'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value

class StavesConverter(BaseConverter):

    def __init__(self, url_map):
        super(StavesConverter, self).__init__(url_map)

        self.regex = r'(?:((all|((start|end|\d+(\.\d+)?)(-(start|end|\d+(\.\d+)?))?))+(,|$))+)'

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value

class MeasuresConverter(BaseConverter):

    def __init__(self, url_map):
        super(MeasuresConverter, self).__init__(url_map)

        self.regex = "(?:((all|((start|end|\d+(\.\d+)?)(-(start|end|\d+(\.\d+)?))?\+?))+(,|$)))"

    def to_python(self, value):
        return value

    def to_url(self, value):
        return value  

class BeatsConverter(BaseConverter):

    def __init__(self, url_map):
        super(BeatsConverter, self).__init__(url_map)

        self.regex = "(?:((@(all|((start|end|\d+(\.\d+)?)(-(start|end|\d+(\.\d+)?))?\+?)))+(,|$)))"

        def to_python(self, value):
            return value

        def to_url(self, value):
            return value 

app.url_map.converters['onex'] = OneOrMixedConverter
app.url_map.converters['oner'] = OneOrRangeConverter
app.url_map.converters['staves'] = StavesConverter
app.url_map.converters['measures'] = MeasuresConverter
app.url_map.converters['beats'] = BeatsConverter


def get_external_mei(meiaddr):
    r = requests.get(unquote(meiaddr), timeout=15)
    # Exeunt stage left if something went wrong.
    if r.status_code != requests.codes.ok:
        if r.status_code == 404:
            raise CannotAccessRemoteMEIException("The MEI File could not be found")
        else:
            raise UnknownMEIReadException("An unknown error ocurred. Status code: {0}".format(r.status_code))

    return r.content


@app.route('/', methods=['GET'])
def index():
    return {'hello': 'world'}


@app.route('/<path:meipath>/<staves:staves>/<measures:measures>/<beats:beats>', methods=["GET"])
@app.route('/<path:meipath>/<staves:staves>/<measures:measures>/<beats:beats>/<completeness>', methods=["GET"])
def address(meipath, measures, staves, beats, completeness=None):
    mei_as_text = get_external_mei(meipath)

    try:
        parsed_mei = meiinfo.read_MEI(mei_as_text)
    except CannotReadMEIException as ex:
        return {"message": ex.message}, status.HTTP_500_INTERNAL_SERVER_ERROR

    try:
        mei_slice = meislicer.MeiSlicer(parsed_mei, measures, staves, beats, completeness).select()
    except BadApiRequest as ex:
        return {"message": ex.message}, status.HTTP_400_BAD_REQUEST
    except UnsupportedEncoding as ex:
        return {"message": ex.message}, status.HTTP_500_INTERNAL_SERVER_ERROR

    # this will write it to a temporary directory automatically
    try:
        filename = meiinfo.write_MEI(mei_slice)
    except CannotWriteMEIException as ex:
        return {"message": ex.message}, status.HTTP_500_INTERNAL_SERVER_ERROR

    return send_file(filename, as_attachment=True, mimetype="application/xml")


@app.route('/<path:meipath>/info.json', methods=['GET'])
def information(meipath):
    try:
        mei_as_text = get_external_mei(meipath)
    except CannotAccessRemoteMEIException as ex:
        return {"message": ex.message}, status.HTTP_400_BAD_REQUEST
    except UnknownMEIReadException as ex:
        return {"message": ex.message}, status.HTTP_500_INTERNAL_SERVER_ERROR

    try:
        parsed_mei = meiinfo.read_MEI(mei_as_text)
    except CannotReadMEIException as ex:
        # return a 500 server error with the exception message
        return {"message": ex.message}, status.HTTP_500_INTERNAL_SERVER_ERROR

    # it's possible that this will raise some exceptions too, so break it out.
    try:
        mus_doc_info = meiinfo.MusDocInfo(parsed_mei).get()
    except BadApiRequest as ex:
        return {"message": ex.message}, status.HTTP_500_INTERNAL_SERVER_ERROR

    return mus_doc_info


if __name__ == "__main__":
    app.run(debug=True)
