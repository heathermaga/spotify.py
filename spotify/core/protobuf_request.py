from spotify.core.request import Request
from spotify.proto.mercury_pb2 import MercuryRequest, MercuryReply
import base64
import httplib
import logging

log = logging.getLogger(__name__)


class ProtobufRequest(Request):
    def __init__(self, name, requests, schema_response, header=None, schema_payload=None):
        super(ProtobufRequest, self).__init__(name, None)

        self.schema_response = schema_response
        self.schema_payload = schema_payload

        self.request = None
        self.payload = None

        self.prepare(requests, header)

    def prepare(self, requests, header=None):
        request = None
        payload = None

        if len(requests) == 1:
            request = self.prepare_single(requests[0])
        elif len(requests) > 1:
            if header is None:
                raise ValueError('A header is required to send multiple requests')

            header['contentType'] = 'vnd.spotify/mercury-mget-request'

            request, payload = self.prepare_multi(header, requests)
        else:
            raise ValueError('At least one request is required')

        self.request = request
        self.payload = payload

    def prepare_single(self, request):
        m_request = MercuryRequest()

        # Fill MercuryRequest
        m_request.uri = request.get('uri', '')
        m_request.content_type = request.get('content_type', '')
        m_request.method = request.get('method', '')
        m_request.source = request.get('source', '')

        return m_request

    def prepare_multi(self, header, requests):
        request = self.prepare_single(header)
        payload = [self.prepare_single(r) for r in requests]

        return request, payload

    def process(self, data):
        result = data['result']

        header = MercuryRequest()
        header.ParseFromString(base64.b64decode(result[0]))

        if 400 < header.status_code < 600:
            message = httplib.responses[header.status_code] or 'Unknown Error'

            if 400 <= header.status_code < 500:
                self.emit('error', 'Client Error: %s (%s)' % (message, header.status_code))
            elif 500 <= header.status_code < 600:
                self.emit('error', 'Server Error: %s (%s)' % (message, header.status_code))

            return

        if self.payload and header.content_type != 'vnd.spotify/mercury-mget-reply':
            self.emit('error', 'Server Error: Server didn\'t send a multi-GET reply for a multi-GET request!')

        self.parse(header.content_type, base64.b64decode(result[1]))

    def parse(self, content_type, data):
        parser_cls = self.schema_response

        if content_type == 'vnd.spotify/mercury-mget-reply':
            raise NotImplementedError()
        else:
            if type(parser_cls) is dict:
                parser_cls = parser_cls.get(content_type)

            if parser_cls is None:
                self.emit('error', 'Unrecognized metadata type: "%s"' % content_type)
                return

            self.emit('success', parser_cls.parse(data))

    def build(self, seq):
        self.args = [
            self.get_number(self.request.method),
            base64.b64encode(self.request.SerializeToString())
        ]

        if self.payload:
            self.args.append(base64.b64encode(self.payload.SerializeToString()))

        return super(ProtobufRequest, self).build(seq)

    def get_number(self, method):
        if method == 'SUB':
            return 1

        if method == 'UNSUB':
            return 2

        return 0
