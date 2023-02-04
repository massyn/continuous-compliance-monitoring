from http.cookies import SimpleCookie
import base64
from urllib import parse
import json
import binascii
import hmac
import hashlib
import datetime
import urllib.request
import urllib.parse
import base64

class lambdaCGI:
    def __init__(self,event):

        # == build SERVER variables
        self.SERVER = {
            'REMOTE_ADDR'       : event['requestContext']['http']['sourceIp'],
            'HTTP_USER_AGENT'   : event['requestContext']['http']['userAgent'],
            'REQUEST_METHOD'    : event['requestContext']['http']['method'],
            'SCRIPT_URI'        : event['requestContext']['http']['path'],
            'SERVER_PROTOCOL'   : event['requestContext']['http']['protocol'],
            'QUERY_STRING'      : event['rawQueryString'],
            'SERVER_NAME'       : event.get('host'),
            'HTTP_REFERER'      : event.get('referer')
        }
        
        # == read the cookies
        cookie = SimpleCookie()
        cookie.load(event.get('headers',{}).get('cookie',''))
        x = {k: v.value for k, v in cookie.items()}
        try:
            self.cookies = json.loads(base64.b64decode(x.get('mySessionCookie','')))
        except:
            print(' * could not read the cookie **')
            self.cookies = {}

        # == read the post variables
        if event.get('isBase64Encoded'):
            body = base64.b64decode(event.get('body',b'')).decode('UTF-8')
        else:
            body = event.get('body',b'').decode('UTF-8')
        self.parsedBody = parse.parse_qs(body)

        # == read the GET variables
        self.getVariables = event.get('queryStringParameters',{})

        self.statusCode = 200

    def GET(self,key):
        return self.getVariables.get(key,'')

    def POST(self,key):
        return self.parsedBody.get(key,[''])[0]

    def setCookie(self,key,value):
        self.cookies[key] = value
    
    def getCookie(self,key):
        return self.cookies.get(key,'')

    def eatCookie(self,key):
        self.setCookie(key,'')
        #if key in self.cookies:
        #    del self.cookies[key]

    def render(self,content = 'No content defined'):

        ck = str(base64.urlsafe_b64encode(json.dumps(self.cookies).encode("utf-8")),"utf-8")

        return {
            'statusCode': self.statusCode,
            'headers': {
                'Content-Type': 'text/html',
                'Set-Cookie' : f"mySessionCookie={ck}; Secure; HttpOnly;",
            },
            'body': content
        }

    def redirect(self,target):

        return {
            'statusCode': 302,
            'headers': {
                'Location': target
            }
        }

    # ============= Cognito Integration code =========
    
    def loggedOn(self,config):
        result = False
        try:
            sessionValid = datetime.datetime.strptime(self.getCookie('sessionTimeout'), '%Y-%m-%d %H:%M:%S') > datetime.datetime.now()
        except:
            sessionValid = False

        thisToken = self.create_sha256_signature(config['client_secret'], self.getCookie('sessionTimeout') + ':' + self.getCookie('sessionUsername'))
        
        if self.getCookie('sessionToken') == thisToken and sessionValid:
            result = True

            # == did we request a logout?
            if self.GET('logout') == 'true':
                self.eatCookie('sessionToken')
                self.eatCookie('sessionTimeout')
                self.eatCookie('sessionUsername')
                result = False

        return result

    def create_sha256_signature(self,key, message):
        byte_key = binascii.unhexlify(hashlib.sha256(key.encode('utf-8')).hexdigest())
        message = message.encode()
        return hmac.new(byte_key, message, hashlib.sha256).hexdigest().upper()

    def authenticate(self,config):
        if not self.GET('code'):
            url = f"{config['cognito_domain']}/login?client_id={config['client_id']}&redirect_uri={config['redirect_uri']}&response_type=code"
            return self.redirect(url)
        else:
            # == generate the token
            code = self.GET('code')
            auth = str(base64.b64encode(f"{config['client_id']}:{config['client_secret']}".encode('utf-8')),'utf-8')
            req = urllib.request.Request(
                f"{config['cognito_domain']}/oauth2/token?grant_type=authorization_code&client_id={config['client_id']}&code={code}&redirect_uri={config['redirect_uri']}",
                data = {},
                headers = {   
                    'Content-Type': 'application/x-www-form-urlencoded',
                    'Authorization' : f'Basic {auth}'
                }
            )
            resp = urllib.request.urlopen(req)
            access_token = json.loads(resp.read())['access_token']

            # == retrieve the user name
            req = urllib.request.Request(
                f"{config['cognito_domain']}/oauth2/userInfo",
                headers = {   
                    'Accept': 'application/json',
                    'Authorization' : f'Bearer {access_token}'
                }
            )
            resp = urllib.request.urlopen(req)
            email = json.loads(resp.read())['email']

            sessionTimeout = (datetime.datetime.now() + datetime.timedelta(hours = 2)).strftime('%Y-%m-%d %H:%M:%S')
            self.setCookie('sessionTimeout',sessionTimeout)
            self.setCookie('sessionUsername',email)
            self.setCookie('sessionToken',self.create_sha256_signature(config['client_secret'],f"{sessionTimeout}:{email}"))
            
            return True