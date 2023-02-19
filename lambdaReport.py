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

def mainDashboard(data,slot,hierarchy,thistotal):
    out = '<table border=1><tr>'
    out += '<tr><th>ID</th>'
    out += '<th>Title</th>'
    out += '<th>Weight</th>'
    out += '<th>Target</th>'
    out += '<th colspan=2>Score</th>'
    out += '</tr>'
    for id in data:
        out += '<tr>'
        out += f'<td><a href="?slot={slot}&hierarchy={hierarchy}&id={id}">{id}</td>'
        out += f"<td>{data[id]['title']}</td>"
        out += f"<td>{data[id]['weight']}</td>"
        out += f"<td>{data[id]['target']:.2%}</td>"
        if not 'score' in data[id]:
            out += '<td> ** No data **</td>'
        else:
            if data[id].get('target',0.9) <= data[id]['score']:
                tdclass = 'ok'
            else:
                tdclass = 'error'
            out += f"<td class={tdclass}>{float(data[id]['score']):.2%}</td><td><progress id=\"{id}\" max=\"100\" value=\"{float(data[id]['score'])*100:.2}\"> {float(data[id]['score'])*100:.2} </progress></td>"

        out += '</tr>\n'

    # TODO -- the global target should be somewhere
    if 0.9 <= float(thistotal) / 100:
        tdclass = 'ok'
    else:
        tdclass = 'error'
    out += f'<tr><th colspan=4>Total</th><td colspan=2 class={tdclass}>{(float(thistotal) / 100):.2%}</td></tr>'
    out += '</table>'

    return out

def xxxproduceHierarchyLookupTable(hierarchy):
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

def reportNavigator(cgi, hierarchyData,summary):
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
    for x in last12slots("{:04d}-{:02d}".format(datetime.date.today().year,datetime.date.today().month)):
        if slot == x:
            html += f'<option value="{x}" selected>{x}</option>'
        else:
            html += f'<option value="{x}">{x}</option>'
    html += '</select>'

    # == show the IDs
    html += '<select name=id>'
    html += f'<option value="">-- Main screen --</option>'
    for myid in summary:
        this = summary[myid]
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

    return (html,compliance)

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
    #html += f"<tr><th>Timestamp</th><td>{metric.get('timestamp','no timestamp')}</td>"
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
        s3 = boto3.client('s3', region_name = os.environ['AWS_REGION'])

        # -- read the slot from the variables
        slot = cgi.GET('slot')
        if slot == None or slot == '':
            slot = "{:04d}-{:02d}".format(datetime.date.today().year,datetime.date.today().month)

        # -- read the hierarchy from the input
        hierarchy = cgi.GET('hierarchy')
        if hierarchy == None or hierarchy == '':
            hierarchy = '/'

        hierarchyList = []
        # == grab the aggregate file for each month - it will form the basis of the report queries
        summary = {}
        mgt = {}
        last = {}
        ps = 'xxxxx'  # grab the last value
        for mySlot in last12slots(slot):
            # == grab the metrics file
            try:
                metric = json.loads(s3.get_object(Bucket=os.environ['S3RepositoryBucket'], Key=f"{mySlot}/metric.json")['Body'].read().decode('utf-8'))
            except:
                metric = {}
            try:
                agg = json.loads(s3.get_object(Bucket=os.environ['S3RepositoryBucket'], Key=f"{mySlot}/aggregate.json")['Body'].read().decode('utf-8'))
                error = ''
            except:
                agg = {}

            if not mySlot in summary:
                summary[mySlot] = {}

            # -- build the hierarchyList
            for h in agg:
                if not h in hierarchyList:
                    hierarchyList.append(h)

            if hierarchy in agg:
                # -- merge the metric data into the summary
                
                for id in agg[hierarchy]:
                    myMetric = {}
                    for m in metric:
                        if m.get('id') == id:
                            summary[mySlot][id] = {
                                'totalok' : agg[hierarchy][id][0],
                                'total'   : agg[hierarchy][id][1],
                                'score'   : (agg[hierarchy][id][0] / agg[hierarchy][id][1]) if agg[hierarchy][id][1] != 0 else -1,
                                'weight'  : m['weight'],
                                'target'  : m['target'],
                                'title'   : m['title']
                            }
            
            # == calculate the SCI score now
            totalscore = 0.0
            totalweight = 0
            for id in summary[mySlot]:
                M = summary[mySlot][id]
                if M.get('score',-1) != -1:
                    totalscore += M['score'] * M['weight']
                    totalweight += M['weight']

            if totalweight != 0:
                thistotal = totalscore / totalweight
            else:
                thistotal = 0
            mgt[mySlot] = "{:.2f}".format(thistotal * 100)
            last[mySlot] = mgt.get(ps,0)
            ps = mySlot
            
        # === if you made it this far, you now have all the information necessary to produce the dashboards
        # -- agg by slot by measure id has all the measure details
        # -- mgt has the total calculated score for every slot

        (navHTML,myCompliance) = reportNavigator(cgi,hierarchyList,summary[slot])

        metricDB = mainDashboard(summary[slot],slot,hierarchy,mgt[slot])
        
        if cgi.GET('id') == '':
            # main page
            management = '\n'.join(template['management']).replace('%TABLE%',metricDB).replace('%DATA%',json.dumps(mgt).replace("\"","'")).replace('%SLOT%',slot).replace('%VALUE%',str(mgt[slot])).replace('%DELTA%',str(last.get(slot,0)))
        else:
            # metric page
            # -- calculate the metric's last 12 month's data
            metricHistory = {}
            id = cgi.GET('id')
            for thisSlot in last12slots(slot):
                if id in summary[thisSlot]:
                    if summary[thisSlot][id].get('total',0) != 0:
                        pct = summary[thisSlot][id].get('totalok',0) / summary[thisSlot][id].get('total',0)
                    else:
                        pct = 0.0
                else:
                    pct = 0.0

                metricHistory[thisSlot] = "{:.2f}".format(pct * 100)

            # render the rest of the data
            myMetric = summary[slot].get(id,{})
            
            management = renderEvidence(s3,slot,hierarchy,id,myMetric,myCompliance,metricHistory,template)

            #management += '<pre>' + json.dumps(summary[slot],indent=4) + '</pre>'

        content = f"<p>{navHTML}<p></p>{management}"
    
    return cgi.render(f"{header}{content}{footer}")

def last12slots(mySlot):
    now = datetime.datetime.strptime(mySlot, '%Y-%m')

    result = [now.strftime("%Y-%m")]
    for _ in range(0, 11):
        now = now.replace(day=1) - datetime.timedelta(days=1)
        result.append(now.strftime('%Y-%m'))
        
    return reversed(result)

# ================================

if __name__ == '__main__':
    for x in last12slots('2022-10'):
        print(x)
    