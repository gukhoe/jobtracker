"""Evidence-based public ATS feeds and optional Brave web discovery."""
import html
import re
from urllib.parse import quote
from .ai import request_json

def plain(value):
    return html.unescape(re.sub('<[^>]+>', ' ', value or ''))

def fetch_feed(feed, transport=request_json):
    slug = quote(feed['board'].strip(), safe='')
    if feed['type'] == 'Lever':
        raw = transport('https://api.lever.co/v0/postings/' + slug + '?mode=json')
        return [dict(company=feed['company'], title=r['text'], location=r.get('categories',{}).get('location',''), url=r['hostedUrl'], source_key='lever:' + slug + ':' + r['id'], description=plain(r.get('description','')) + '\n' + '\n'.join(plain(x.get('content','')) for x in r.get('lists',[])), availability='open', source='Lever public company feed', salary_basis='unknown', currency='', salary_min=None, salary_max=None) for r in raw]
    if feed['type'] == 'Greenhouse':
        raw = transport('https://boards-api.greenhouse.io/v1/boards/' + slug + '/jobs?content=true')
        return [dict(company=feed['company'],title=r['title'],location=r.get('location',{}).get('name',''),url=r['absolute_url'],source_key='greenhouse:' + slug + ':' + str(r['id']),description=plain(r.get('content','')), availability='open',source='Greenhouse public company feed',salary_basis='unknown',currency='',salary_min=None,salary_max=None) for r in raw['jobs']]
    raise ValueError('Supported feeds: Lever and Greenhouse.')

def matches(job, profile):
    text = (job.get('title','') + ' ' + job.get('description','')).casefold()
    roles = [x.strip().casefold() for x in profile.get('keywords','').split(',') if x.strip()]
    locations = [x.strip().casefold() for x in profile.get('locations','').split(',') if x.strip()]
    return (not roles or any(x in text for x in roles)) and (not locations or any(x in job.get('location','').casefold() for x in locations))

def web_search(query, key, transport=request_json):
    if not key:
        raise ValueError('Configure a Brave Search API key to enable open-web discovery.')
    result = transport('https://api.search.brave.com/res/v1/web/search?q=' + quote(query) + '&count=10', None, {'X-Subscription-Token':key})
    return [dict(title=r.get('title',''),url=r['url'],snippet=plain(r.get('description',''))) for r in result.get('web',{}).get('results',[])]
