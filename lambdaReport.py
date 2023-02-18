import boto3
import json
import os
import datetime

from lambdaCGI import lambdaCGI

import hmac
import hashlib 
import binascii

def create_sha256_signature(key, message):
    byte_key = binascii.unhexlify(key)
    message = message.encode()
    return hmac.new(byte_key, message, hashlib.sha256).hexdigest().upper()

def error(txt):
    return {
        'statusCode': 403,
        'headers': {'Content-Type': 'text/html'},
        'body': f"<!DOCTYPE html><html lang=\"en\"><body><p>{txt}</p></body></html>"
    }

def todo_weighted_score(value,target):
    pivotpoint = 0.9
    if value <= target:
        return value /  target * pivotpoint
    else:
        return (( value - target) / (1- target ) * (1 - pivotpoint) )+ pivotpoint

def calculateSCI(data):
    totalscore = 0.0
    totalweight = 0
    for M in data:
        if M['timestamp'] != None:
            totalscore += M['score']
            totalweight += M['weight']
    if totalweight != 0:
        thistotal = totalscore / totalweight
    else:
        thistotal = 0
    return thistotal

def mainDashboard(data,slot,hierarchy):

    q = [ 'id','title','timestamp','weight','target', 'score']

    out = '<table border=1><tr>'
    for a in q:
        if a == 'score':
            out += f"<th colpan=2>{a}</th>"
        else:
            out += f"<th>{a}</th>"
    out += '</tr>'

    for M in data:
        out += '<tr>'
        for r in q:
            if r == 'id':
                out += f'<td><a href="?slot={slot}&hierarchy={hierarchy}&id={M[r]}">{M[r]}</td>'
            elif r == 'score':
                if M.get('target',0.9) <= M['score']:
                    tdclass = 'ok'
                else:
                    tdclass = 'error'
                out += f"<td class={tdclass}>{float(M['score']):.2%}</td><td><progress id=\"{M['id']}\" max=\"100\" value=\"{float(M['score'])*100:.2}\"> {float(M['score'])*100:.2} </progress></td>"
            elif r == 'target':
                out += f"<td>{M['target']:.2%}</td>"
            elif r == 'timestamp':
                if M['timestamp'] == None:
                    out += "<td>No upload received</td>"
                else:
                    out += f"<td>{datetime.datetime.strptime(M['timestamp'], '%Y-%m-%d %H:%M:%S')}</td>"
            else:
                out += f'<td>{M[r]}</td>'

        out += '</tr>'
    thistotal =  calculateSCI(data)

    # TODO -- the global target should be somewhere
    if 0.9 <= thistotal:
        tdclass = 'ok'
    else:
        tdclass = 'error'
    out += f'<tr><th colspan=5>Total</th><td class={tdclass}>{thistotal:.2%}</td></tr>'

    out += '</table>'

    return out

def produceHierarchyLookupTable(hierarchy):
    def leaf(x,H,parent = ''):
        for y in x:
            # The first item is the main leaf.  Anything after that are either alternate names, wildcards, or CIDR addresses
            i = y.split('|')
            me = i[0]
            key = f"{parent}/{me}"

            if not key in H['full']:
                H['full'].append(key)

            if me == '/':
                print(f' ** You cannot have a / in the hierarchy table! -- {y}')
                exit(1)
                return { 'statusCode': 400, 'body': f' ** You cannot have a / in the hierarchy table! -- {y}' }

            # create the children leaf
            if parent == '':
                cParent = '/'
            else:
                cParent = parent

            if not cParent in H['children']:
                H['children'][cParent] = []
            if not key in H['children'][cParent]:
                H['children'][cParent].append(key)

            # Use case - use the hierarchy defined as is
            H["direct"][me] = key

            for a in i:
                if '*' in a:
                    # Use case - a hierarchy leaf could be a wildcard
                    if not a in H['wildcard']:
                        H['wildcard'][a] = key
                elif '/' in a:
                    # Use case - a hierarchy leaf could be an IP address CIDR
                    if not a in H['cidr']:
                        H['cidr'][a] = key
                else:
                    # Use case - a hierarchy leaf could have an alternate name
                    if not a in H['direct']:
                        H['direct'][a] = key

            # TODO - alternate names
            # TODO - Wildcards
            # TODO - CIDR addresses

            if type(x) == dict:
                leaf(x[y],H,key)
            
    H = { "direct" : {}, "wildcard" : {}, "cidr" : {}, "children" : {}, "full" : [] }

    # == add an "Unknown" hierarchy item
    if not 'Unknown' in hierarchy:
        hierarchy["Unknown"] = []

    leaf(hierarchy,H)

    return H

# ListOfMeasures will extract all the raw measure data from the aggregate file, and produce an
# array of all the relevant data necessary to produce an SCI...
def ListOfMeasures(data,hierarchy,slot):
    out = []

    for id in data['hierarchy'].get(hierarchy,{}).get(slot,{}):
        this = data['hierarchy'][hierarchy][slot][id]
        if this.get('status',True):
            # == calculate the score
            if this.get('total',0) != 0:
                pct = this.get('totalok',0) / this.get('total',0)
            else:
                pct = 0
            out.append({
                'id'        : id,
                'title'     : this.get('title',id),
                'weight'    : this.get('weight',1),
                'target'    : this.get('target',0.95),
                'totalok'   : this['totalok'],
                'total'     : this['total'],
                'timestamp' : this['timestamp'],
                'score'     : pct
            })

    return out

def reportNavigator(cgi, hierarchyData):
    #slot = event.get('queryStringParameters',{}).get('slot',"{:04d}-{:02d}".format(datetime.date.today().year,datetime.date.today().month))
    slot = cgi.GET('slot')
    hierarchy = cgi.GET('hierarchy')
    id = cgi.GET('id')
    compliance = cgi.GET('compliance')

    if slot == None or slot == '':
        slot = "{:04d}-{:02d}".format(datetime.date.today().year,datetime.date.today().month)
    if hierarchy == None or hierarchy not in hierarchyData:
        hierarchy = '/'

    html = '<form method=get>'
    html += '<select name=hierarchy>'
    for x in hierarchyData:
        if hierarchy == x:
            html += f'<option value="{x}" selected>{x}</option>'
        else:
            html += f'<option value="{x}">{x}</option>'
    html += '</select>'
    html += '<select name=slot>'
    for x in last12slots():
        if slot == x:
            html += f'<option value="{x}" selected>{x}</option>'
        else:
            html += f'<option value="{x}">{x}</option>'
    html += '</select>'

    # == show the IDs
    html += '<select name=id>'
    html += f'<option value="">-- Main screen --</option>'
    for myid in hierarchyData.get(hierarchy,{}).get(slot,{}):
        this = hierarchyData[hierarchy][slot][myid]
        if this.get('status',True):
            title = this.get('title',myid)
            if myid == id:
                html += f'<option value="{myid}" selected>{myid} - {title}</option>'
            else:
                html += f'<option value="{myid}">{myid} - {title}</option>'

    html += '</select>'

    # == show what is compliant
    opt = [ [ '','All' ],
            [ '1','Compliant'] ,
            [ '0','Non-Compliant'] ,
            ['-1','Skipped']
    ]

    html += '<select name=compliance>'
    for (x,y) in opt:
        if x == compliance:
            html += f'<option value="{x}" selected>{y}</option>'
        else:
            html += f'<option value="{x}">{y}</option>'

    html += '</select>'

    html += '<input type=submit>'
    html += '</form>'

    return (slot,hierarchy,html,compliance)

def renderEvidence(s3,slot,hierarchy,id,metric,myCompliance,myMetricHistory,template):
    try:
        detail = json.loads(s3.get_object(Bucket=os.environ['S3RepositoryBucket'], Key=f'{slot}/{id}/detail.json')['Body'].read().decode('utf-8'))
    except:
        detail = {}

    if metric.get('total',0) != 0:
        pct = metric.get('totalok',0) / metric.get('total',0)
    else:
        pct = 0.0

    html = ''
    html += '<h2>Summary</h2>'
    html += "<table border=0><tr><td>"
    html += "<table border=1>"
    html += f"<tr><th>id</th><td>{id}</td>"
    html += f"<tr><th>Title</th><td>{metric.get('title','no title')}</td>"
    html += f"<tr><th>Timestamp</th><td>{metric.get('timestamp','no timestamp')}</td>"
    html += f"<tr><th>Score</th><td>{metric.get('totalok','no totalok')} / {metric.get('total','no total')} = {pct:.2%}</td>"
    html += f"<tr><th>Weight</th><td>{metric.get('weight',-1)}</td>"
    html += f"<tr><th>Target</th><td>{metric.get('target',0):.2%}</td>"
    html += "</table>"
    html += "</td><td>"

    html += '\n'.join(template['trend']).replace('%DATA%',json.dumps(myMetricHistory).replace("\"","'")).replace('%SLOT%',slot)
    html += "</td></table>"
    html += '<h2>Evidence</h2>'
    if not 'heads' in detail:
        return 'Unable to read the detail file'
    else:
        # == render the headers
        compliance = -1
        c = 0
        html += '<table border=1><tr>'
        for h in detail['heads']:
            if h == 'compliance':
                compliance = c
            html += f"<th>{h}</th>"
            c += 1
        html += '</tr>'

        # == find the evidence
        for h in detail['detail']:
            if h.startswith(hierarchy):
                thisCompliance = 0
                for i in detail['detail'][h]:
                    row = '<tr>'
                    c = 0
                    for d in i:
                        if c == compliance:
                            thisCompliance = d
                            if float(d) == 1.0:
                                tdclass = 'ok'
                            elif float(d) == -1.0:
                                tdclass = 'neutral'
                            else:
                                tdclass = 'error'
                        else:
                            tdclass = 'normal'

                        row += f'<td class={tdclass}>{d}</td>'
                        c += 1
                    row += '</tr>'

                    # the filter works as follow
                    # - if compliance is empty, we show All
                    # - if set to 1, we only show "Compliance"
                    # - if set to 0, we show everything that is non-compliant.  The trick however is that the compliance field is a float that can be between 0 and 1        
                    if myCompliance == '' or (myCompliance == '1' and float(thisCompliance) == 1.0) or (myCompliance == '0' and float(thisCompliance) != 1.0 and float(thisCompliance) != -1.0)or (myCompliance == '-1' and float(thisCompliance) == -1.0):
                        html += row
        html += '</table>'

        return html


    #return '<pre>' + json.dumps(detail,indent=4) + '</pre>'

def lambda_handler(event, context):

    cgi = lambdaCGI(event)

    with open('template.json','rt') as t:
        template = json.load(t)

    with open('config.json','rt') as t:
        config = json.load(t)

    header = '\n'.join(template['header'])
    footer = '\n'.join(template['footer'])

    loggedon = False
    if cgi.loggedOn(config):
        loggedon = True
        #status = "we are logged on " + cgi.getCookie('sessionUsername')
    else:
        x = cgi.authenticate(config)
        if x != True:
            return x
        else:
            loggedon = True

    # =====================================================================
    if loggedon:
        # == grab the aggregate file - it will form the basis of the report queries
        s3 = boto3.client('s3', region_name = os.environ['AWS_REGION'])
        try:
            agg = json.loads(s3.get_object(Bucket=os.environ['S3RepositoryBucket'], Key='aggregate.json')['Body'].read().decode('utf-8'))
            error = ''
        except:
            agg = {}
            error = 'Something went wrong getting the aggregate file'

        (slot,myHierarchyLevel,navHTML,myCompliance) = reportNavigator(cgi,agg['hierarchy'])

        measuredata = ListOfMeasures(agg,myHierarchyLevel,slot)

        metricDB = mainDashboard(measuredata,slot,myHierarchyLevel)

        mgt = {}
        last = {}
        ps = 'xxxxx'  # grab the last value
        for s in last12slots():
            
            md = ListOfMeasures(agg,myHierarchyLevel,s)
            mgt[s] = "{:.2f}".format(calculateSCI(md) * 100)
            last[s] = mgt.get(ps,0)
            ps = s

        if cgi.GET('id') == '':
            # main page
            management = '\n'.join(template['management']).replace('%TABLE%',metricDB).replace('%DATA%',json.dumps(mgt).replace("\"","'")).replace('%SLOT%',slot).replace('%VALUE%',str(mgt[slot])).replace('%DELTA%',str(last.get(slot,0)))
        else:
            # metric page
            # -- calculate the metric's last 12 month's data
            metricHistory = {}
            for thisSlot in last12slots():
                thisMetric = agg['hierarchy'].get(myHierarchyLevel,{}).get(thisSlot,{}).get(cgi.GET('id'),{})
                if thisMetric.get('total',0) != 0:
                    pct = thisMetric.get('totalok',0) / thisMetric.get('total',0)
                else:
                    pct = 0.0

                metricHistory[thisSlot] = "{:.2f}".format(pct * 100)

            # render the rest of the data
            myMetric = agg['hierarchy'].get(myHierarchyLevel,{}).get(slot,{}).get(cgi.GET('id'),{})
            management = renderEvidence(s3,slot,myHierarchyLevel,cgi.GET('id'),myMetric,myCompliance,metricHistory,template)

        content = f"<p>{navHTML}<p><b>{error}</b></p>{management}"
    
    return cgi.render(f"{header}{content}{footer}")

def last12slots():
    now = datetime.datetime.now()
    result = [now.strftime("%Y-%m")]
    for _ in range(0, 11):
        now = now.replace(day=1) - datetime.timedelta(days=1)
        result.append(now.strftime('%Y-%m'))
        
    return reversed(result)
