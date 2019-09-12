# coding=utf-8
import sys
import os
import json
from glob import glob
from jsonpath_rw import jsonpath, parse
from itertools import ifilter

FOR_RESULT_DOC_ADDITIONAL_PARAMS = 'additionalParams'
FOR_RESULT_DOC_NESTED_ADDITIONAL_PARAMS = 'nestedAdditionalParams'
TEMPLATE = 'template'

ADDITIONAL_PARAM = 'additionalParam'
ADDITIONAL_PARAMS_FOR_NS = 'additionalParamForNs'
ADDITIONAL_PARAMS_FOR_VNF = 'additionalParamForVnf'
ADDITIONAL_PARAMS_FOR_NESTED_NS = 'additionalParamForNestedNs'

VNF_PROFILE = 'vnfProfileId'
NS_PROFILE = 'nsProfileId'

JSON_TYPE_FILTER = "\\*.json"


# final func
def find_all_paths_to_json():
    print "Start searching all paths to json files.."
    json_path_list = []
    for address, dirs, files in os.walk(os.getcwd()):
        curJ = glob(address + JSON_TYPE_FILTER)
        if len(curJ) > 0:
            for jp in glob(address + JSON_TYPE_FILTER):
                json_path_list.append(jp)
    print "End searching. This jsons will be changed: \n" + str(json_path_list)
    return json_path_list


def by_files(json_path_list):
    for pathToJson in json_path_list:
        print "Start work with json file: " + pathToJson
        with open(pathToJson) as json_file:
            data = json.load(json_file)

        print "End work with json file."


# ---------------------------

def get_value_by_path(data, path):
    if len(path) == 1:
        return data[path[0]]
    else:
        return get_value_by_path(data[path.pop(0)], path)


def set_value_by_path(data, path, target):
    if len(path) == 1:
        data[path[0]] = target
        return
    else:
        set_value_by_path(data[path.pop(0)], path, target)


def delete_child_by_path(data, path):
    if len(path) == 1:
        data.pop(path[0])
        return
    if len(path) == 2:
        data[path[0]].pop(path[1])
        return
    else:
        delete_child_by_path(data[path.pop(0)], path)


def find_nested_params_for_ns_by_ns_path_lvl(path, entity_list):
    path_to_ns_lvl = ''.join(str(path).split('.')[:-1])
    for entity_dict in entity_list:
        for entity_path, entity_value in entity_dict.items():
            tmp = ''.join(str(entity_path).split('.')[:-1])
            if tmp == path_to_ns_lvl:
                return dict({entity_path: entity_value})


def get_internal_ap(data):
    iap = {}
    if data.get(ADDITIONAL_PARAM):
        iap = data.pop(ADDITIONAL_PARAM)
    iap.update(data)
    return iap


def create_root(data):
    root_additional_param = get_internal_ap(data)
    root_additional_param.update({FOR_RESULT_DOC_NESTED_ADDITIONAL_PARAMS: []})
    return root_additional_param


def create_vnf(data):
    vnf = {
        TEMPLATE: data.pop(VNF_PROFILE),
        FOR_RESULT_DOC_ADDITIONAL_PARAMS: get_internal_ap(data)
    }
    return vnf


def extract_vnfs(data):
    vnfs = list()
    for item in data:
        vnfs.append(create_vnf(item))
    return vnfs


def create_nested_ns(data):
    ns = {TEMPLATE: data.pop(NS_PROFILE), FOR_RESULT_DOC_ADDITIONAL_PARAMS: {}}
    if data.get(ADDITIONAL_PARAMS_FOR_VNF):
        ns[FOR_RESULT_DOC_ADDITIONAL_PARAMS][FOR_RESULT_DOC_NESTED_ADDITIONAL_PARAMS] = extract_vnfs(
            data.pop(ADDITIONAL_PARAMS_FOR_VNF))
    ns[FOR_RESULT_DOC_ADDITIONAL_PARAMS].update(get_internal_ap(data))
    return ns


def extract_nested_nss(data):
    nested_nss = list()
    for item in data:
        nested_nss.append(create_nested_ns(item))
    return nested_nss


# find all NS -> [0:n] transf into root FOR_RESULT_DOC_ADDITIONAL_PARAMS >
# > find all VNF for cur NS by path (relative NS and VNF state by once lvl) >
# > added VNF into FOR_RESULT_DOC_NESTED_ADDITIONAL_PARAMS >
# > find Nested NS and repeat operation as for NS
def transfiguration(data):
    # 1. find all NS:
    root_ns_list = [{match.full_path: match.value} for match in parse('$..%s' % ADDITIONAL_PARAMS_FOR_NS).find(data)]
    result = dict()
    # 2. walk by list of NS dict for extract pair {pathToNs:NsValue}
    for root_ns_dict in root_ns_list:
        # 3. walk by NS dict for start creating root AP and nested AP for every NS
        for paths, values in root_ns_dict.items():
            tmp_root_ap = create_root(values)
            # 4. find VNF AP
            root_vnf_list = [{match.full_path: match.value} for match in
                             parse('$..%s' % ADDITIONAL_PARAMS_FOR_VNF).find(data)]
            # 5. extract VNF AP which are only at the NS AP level
            root_vnf_ = find_nested_params_for_ns_by_ns_path_lvl(paths, root_vnf_list)
            # 6. find nested NS AP
            nested_nss_list = [{match.full_path: match.value} for match in
                               parse('$..%s' % ADDITIONAL_PARAMS_FOR_NESTED_NS).find(data)]
            # 7. extract nested NS AP which are only at the NS level
            nested_nss_ = find_nested_params_for_ns_by_ns_path_lvl(paths, nested_nss_list)

            # 8. create nested params for nns and vnf && fill nested ap && delete nns and vnf from source json
            if root_vnf_ is not None:
                ext_nested_vnfs = extract_vnfs(root_vnf_.values()[0])
                tmp_root_ap[FOR_RESULT_DOC_NESTED_ADDITIONAL_PARAMS].extend(ext_nested_vnfs)
                delete_child_by_path(data, root_vnf_.keys()[0].split('.'))

            if nested_nss_ is not None:
                ext_nested_nss = extract_nested_nss(nested_nss_.values()[0])
                tmp_root_ap[FOR_RESULT_DOC_NESTED_ADDITIONAL_PARAMS].extend(ext_nested_nss)
                delete_child_by_path(data, str(nested_nss_.keys()[0]).split('.'))

            # delete nested nss and vnfs

            result.update({paths: tmp_root_ap})
    return result


# $.attributes.instance.additionalParamForNS{}

def search(data, key, path='$', tmpPath=''):
    # pv = {}
    for k, value in data.items():
        if type(value) is dict and value.get(key):
            path += tmpPath + '.%s' % k
        if k == key:
            pv = {}
            path += '.%s' % k
            pv['path'] = path
            pv['value'] = data.pop(k)
            return pv
        elif type(value) is dict:
            tmpPath += '.%s' % k
            # проброс значения в стеке вызова
            pv = search(value, key, path, tmpPath)
            # условие необх для того, чтобы рекурсия дошла до нужного места
            if type(pv) is dict and len(pv.items()) > 0:
                return pv


def start(data):
    root = dict()
    pathForNS = ''
    search_ns = search(data, ADDITIONAL_PARAMS_FOR_NS, pathForNS)
    # pathForNS = search_ns.get('path')
    ap_ns = search_ns.get('value')
    if ap_ns.get(ADDITIONAL_PARAM):
        root[ADDITIONAL_PARAM] = ap_ns.pop(ADDITIONAL_PARAM)
    root[ADDITIONAL_PARAM].update(ap_ns)

    search_vnf = search(data, ADDITIONAL_PARAMS_FOR_VNF)
    ap_ns[FOR_RESULT_DOC_NESTED_ADDITIONAL_PARAMS] = extract_vnfs(search_vnf.get('value'))
    root[ADDITIONAL_PARAM].update(ap_ns)

    # by path from search_result for APNS added root AP in document

    return root


# print "\nSTART json session transfiguration...\n"
# jsonPathList = findAllPathsToJson()
# byFiles(jsonPathList)
# print "\nEND json session transfiguration!"

# wt = open('C:\\Users\\dmpi0716\\Desktop\\test\\work_test.json')
wt = open(
    'C:\\Users\\dmpi0716\\Desktop\\CloudMANORepositories\\operation-executor\\decomposer\\src\\test\\resources\\stubs\\ns\\instantiateNestedNs\\mrs_instantiate_nested_pure_operation_data.json')

jData = json.load(wt)
work_test = transfiguration(jData)
for path, ap in work_test.items():
    print path
    print json.dumps(ap)


print jData

# tests ----------------------------------------------------------------------------------------------------------------------

# qqq = {"vnfProfile": "VNF1", "q": 1, "w": 2, ADDITIONAL_PARAMS: {"z": 3, "x": 4}}
# qqq2 = {"vnfProfile": "VNF1", ADDITIONAL_PARAMS: {"z": 3, "x": 4}}
#
# ttt = dict()
# ttt[TEMPLATE] = qqq.pop(VNF_PROFILE)
# if qqq.get(ADDITIONAL_PARAMS):
#     ttt[ADDITIONAL_PARAMS] = qqq.pop(ADDITIONAL_PARAMS)
# ttt[ADDITIONAL_PARAMS].update(qqq)
#
# print ttt


# zh = searcher(jData.get(ADDITIONAL_PARAMS_FOR_NESTED_NS), ADDITIONAL_PARAMS_FOR_VNF)
# print json.dumps(zh)

# print "----------------NS----------------"
# ns = [{match.full_path: match.value} for match in parse('$..%s' % ADDITIONAL_PARAMS_FOR_NS).find(jData)]
# ns = [match.full_path for match in parse('$..%s' % ADDITIONAL_PARAMS_FOR_NS).find(jData)]
# print ns
# print len(ns)

# print "---------VNF--------------"
# gVnf = [{match.full_path: match.value} for match in parse("$..%s"%ADDITIONAL_PARAMS_FOR_VNF).find(jData)]
# gVnf = [match.full_path for match in parse("$..%s"%ADDITIONAL_PARAMS_FOR_VNF).find(jData)]
# print gVnf

# print "--------------NNS-------------"
# nns = [{match.full_path: match.value} for match in parse("$..%s"%ADDITIONAL_PARAMS_FOR_NESTED_NS).find(jData)]
# nns = [match.full_path for match in parse("$..%s"%ADDITIONAL_PARAMS_FOR_NESTED_NS).find(jData)]
# print nns

keker = {
    "instantiatedInfo": {
        "additionalParamForNs": 123
    },
    "attributes": {
        "instance": {
            "additionalParamForNs": 234
        },
        "cod": {
            "del": {
                "a": 1,
                "b": 2,
                "test": {
                    "test_a": "del_me",
                    "test_b": "del_me_to"
                }
            },
            "vasya": {
                "zxc": "asd",
                "kek": "shmek"
            }
        }
    }
}
# print keker


# path = 'attributes.cod.del.test'.split('.')
# delete_child_by_path(keker, path)
# print get_value_by_path(keker, path)
# set_value_by_path(keker, path, {"this_change": "CHANGED"})
# print get_value_by_path(keker, path)

# print keker

# tns = [{match.full_path: match.value} for match in parse('$..additionalParamForNs').find(jData)]
# tns = [{match.full_path: match.value} for match in parse('$..additionalParamForVnf').find(jData)]
# tns = [{match.full_path: match.value} for match in parse('$..additionalParamForNestedNs').find(jData)]
# print type(tns)
# for item in tns:
#     for k,v in item.items():
#         print type(k)
#         print type(v)
# print type(tns[0])

# for v in tns:
#     for k, v in v.items():
#         print type(k)
#         print k
#         print type(v)
#         print json.dumps(v)

# v = 'attributes.instance.additionalParamForVnf'
# n = 'attributes.instance.additionalParamForNs'
# vv = ''.join(v.split('.')[:-1])
# print vv
# nn = ''.join(n.split('.')[:-1])
# print nn
# print vv==nn

# for elem in ifilter(lambda x: x['type'] in keyValList, exampleSet):
#     print elem

# keys = str(tns[0].keys()[0]).split('.')
# print get_value_by_path(keker, keys)
#
# set_value_by_path(keker, keys, 'changed')
# print keker

# ph = str(tns[0].keys()[0]).split('.')
# print ph
# print keker[ph[0]][ph[1]]

# check = dict({ADDITIONAL_PARAMS:{"asd":123,"cxv":534, NESTED_ADDITIONAL_PARAMS:[]}})
# l = [1,2,34,5,6,7,8,34,534,51,233,214,32,4]
#
# bg = ["123","dfgdf","vbdfer"]
# check[ADDITIONAL_PARAMS][NESTED_ADDITIONAL_PARAMS].extend(l)
# print check
# check[ADDITIONAL_PARAMS][NESTED_ADDITIONAL_PARAMS].extend(bg)
# print check
