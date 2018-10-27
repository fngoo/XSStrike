#!/usr/bin/env python3

from __future__ import print_function

from core.colors import end, red, white, green, yellow, run, bad, good, info, que

# Just a fancy ass banner
print('''%s
\tXSStrike %sv3.0-beta
%s''' % (red, white, end))

try:
    from urllib.parse import unquote, urlparse
except ImportError: # throws error in python2
    print ('%s XSStrike isn\'t compatible with python2.' % bad)
    quit()

# Let's import whatever we need
import re
import os
import sys
import copy
import argparse
import requests
import webbrowser

import core.config
from core.dom import dom
from core.arjun import arjun
from core.photon import photon
from core.prompt import prompt
from core.fuzzer import fuzzer
from core.updater import updater
from core.checker import checker
from core.generator import generator
from core.requester import requester
from core.htmlParser import htmlParser
from core.wafDetector import wafDetector
from core.filterChecker import filterChecker
from core.config import xsschecker, minEfficiency
from core.utils import getUrl, getParams, flattenParams, extractHeaders

# Processing command line arguments
parser = argparse.ArgumentParser()
parser.add_argument('-u', '--url', help='url', dest='target')
parser.add_argument('--data', help='post data', dest='data')
parser.add_argument('-c', '--cookie', help='cookie', dest='cookie')
parser.add_argument('-t', '--threads', help='number of threads', dest='threads')
parser.add_argument('--fuzzer', help='fuzzer', dest='fuzz', action='store_true')
parser.add_argument('--update', help='update', dest='update', action='store_true')
parser.add_argument('--timeout', help='timeout', dest='timeout', action='store_true')
parser.add_argument('--params', help='find params', dest='find', action='store_true')
parser.add_argument('--crawl', help='crawl', dest='recursive', action='store_true')
parser.add_argument('--skip-poc', help='skip poc generation', dest='skipPOC', action='store_true')
parser.add_argument('--skip-dom', help='skip dom checking', dest='skipDOM', action='store_true')
parser.add_argument('--headers', help='add headers', dest='headers', action='store_true')
parser.add_argument('-d', '--delay', help='delay between requests', dest='delay', type=int)
args = parser.parse_args()

if args.headers:
    headers = extractHeaders(prompt())
else:
    from core.config import headers

find = args.find
fuzz = args.fuzz
target = args.target
cookie = args.cookie
paramData = args.data
skipDOM = args.skipDOM
skipPOC = args.skipPOC
delay = args.delay or core.config.delay
threadCount = args.threads or core.config.threadCount
timeout = args.timeout or core.config.timeout

if args.update: # if the user has supplied --update argument
    updater()
    quit() # quitting because files have been changed

if not target: # if the user hasn't supplied a url
    print('\n' + parser.format_help().lower())
    quit()

def singleTarget(target, paramData):
    if paramData:
        GET, POST = False, True
    else:
        GET, POST = True, False
    # If the user hasn't supplied the root url with http(s), we will handle it
    if target.startswith('http'):
        target = target
    else:
        try:
            response = requests.get('https://' + target)
            target = 'https://' + target
        except:
            target = 'http://' + target
    try:
        response = requests.get(target).text
        if not skipDOM:
            print ('%s Checking for DOM vulnerabilities' % run)
            if dom(response):
                print ('%s Potentially vulnerable objects found' % good)
    except Exception as e:
        print ('%s Unable to connect to the target' % bad)
        print ('%s Error: %s' % (bad, e))
        quit()
    host = urlparse(target).netloc # Extracts host out of the url
    url = getUrl(target, paramData, GET)
    params = getParams(target, paramData, GET)
    if args.find:
        params = arjun(url, GET, headers, delay)
    if not params:
        quit()
    WAF = wafDetector(url, {list(params.keys())[0] : xsschecker}, headers, GET, delay)
    if WAF:
        print ('%s WAF detected: %s%s%s' % (bad, green, WAF, end))
    else:
        print ('%s WAF Status: %sOffline%s' % (good, green, end))

    if fuzz:
        for paramName in params.keys():
            print ('%s Fuzzing parameter: %s' % (info, paramName))
            paramsCopy = copy.deepcopy(params)
            paramsCopy[paramName] = xsschecker
            fuzzer(url, paramsCopy, headers, GET, delay, WAF)
        quit()

    for paramName in params.keys():
        paramsCopy = copy.deepcopy(params)
        print ('%s Testing parameter: %s' % (info, paramName))
        paramsCopy[paramName] = xsschecker
        response = requester(url, paramsCopy, headers, GET, delay).text
        occurences = htmlParser(response)
        if not occurences:
            print ('%s No reflection found' % bad)
            continue
        else:
            print ('%s Reflections found: %s' % (info, len(occurences)))
        print ('%s Analysing reflections' % run)
        efficiencies = filterChecker(url, paramsCopy, headers, GET, delay, occurences)
        print ('%s Generating payloads' % run)
        vectors = generator(occurences, response)
        total = 0
        for v in vectors.values():
            total += len(v)
        if total == 0:
            print ('%s No vectors were crafted' % bad)
            continue
        print ('%s Payloads generated: %i' % (info, total))
        progress = 0
        for confidence, vects in vectors.items():
            for vect in vects:
                progress += 1
                print ('%s Payloads tried [%i/%i]' % (run, progress, total), end='\r')
                if not GET:
                    vect = unquote(vect)
                efficiencies = checker(url, paramsCopy, headers, GET, delay, vect)
                if not efficiencies:
                    for i in range(len(occurences)):
                        efficiencies.append(0)
                bestEfficiency = max(efficiencies)
                if bestEfficiency == 100 or (vect[0] == '\\' and bestEfficiency >= 95):
                    print (('%s-%s' % (red, end)) * 60)
                    print ('%s Payload: %s' % (good, vect))
                    print ('%s Efficiency: %i' % (info, bestEfficiency))
                    print ('%s Cofidence: %i' % (info, confidence))
                    if GET:
                        flatParams = flattenParams(paramName, paramsCopy, vect)
                        if '"' not in flatParams and '}' not in flatParams and not skipPOC:
                            webbrowser.open(url + flatParams)
                    choice = input('%s Would you like to continue scanning? [y/N] ' % que).lower()
                    if choice != 'y':
                        quit()
                elif bestEfficiency > minEfficiency:
                    print (('%s-%s' % (red, end)) * 60)
                    print ('%s Payload: %s' % (good, vect))
                    print ('%s Efficiency: %i' % (info, bestEfficiency))
                    print ('%s Cofidence: %i' % (info, confidence))

if not args.recursive:
    singleTarget(target, paramData)
else:
    print ('%s Crawling the target' % run)
    scheme = urlparse(target).scheme
    host = urlparse(target).netloc
    main_url = scheme + '://' + host
    forms = photon(main_url, target, headers)
    signatures = set()
    for form in forms:
        for each in form.values():
            url = each['action']
            if url:
                if url.startswith(main_url):
                    pass
                elif url.startswith('//') and url[2:].startswith(host):
                    url = scheme + '://' + url[2:]
                elif url.startswith('/'):
                    url = scheme + '://' + host + url
                elif re.match(r'\w', url[0]):
                    url = scheme + '://' + host + '/' + url
                method = each['method']
                if method == 'get':
                    GET = True
                else:
                    GET = False
                inputs = each['inputs']
                paramData = {}
                for one in inputs:
                    paramData[one['name']] = one['value']
                    if target not in ''.join(signatures) and not skipDOM:
                        response = requests.get(target).text
                        if dom(response, silent=True):
                            print ('%s Potentially vulnerable objects found' % good)
                    for paramName in paramData.keys():
                        signature = url + paramName
                        if signature not in signatures:
                            signatures.add(signature)
                            print ('%s Scanning %s%s%s, %s' % (run, green, url, end, paramName))
                            paramsCopy = copy.deepcopy(paramData)
                            paramsCopy[paramName] = xsschecker
                            response = requester(url, paramsCopy, headers, GET, delay).text
                            try:
                                occurences = htmlParser(response)
                                efficiencies = filterChecker(url, paramsCopy, headers, GET, delay, occurences)
                                vectors = generator(occurences, response)
                                if vectors:
                                    for confidence, vects in vectors.items():
                                        try:
                                            print ('%s Vector for %s: %s' % (good, paramName, list(vects)[0]))
                                            break
                                        except IndexError:
                                            pass
                            except Exception as e:
                                print ('%s Error: %s' % (bad, e))
