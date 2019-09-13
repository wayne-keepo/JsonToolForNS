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


def set_key_name_by_path(data, path, newName):
    if len(path) == 1:
        data.update({newName: data.pop(path[0])})
        return
    if len(path) == 2:
        data[path[0]].update({newName: data[path[0]].pop(path[1])})
        return
    else:
        set_key_name_by_path(data[path.pop(0)], path, newName)


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
    print "##########################################################"
    print "START TRANSFIGURATION..."
    print "---------------------"
    print "Start searching all NS..."
    root_ns_list = [{match.full_path: match.value} for match in parse('$..%s' % ADDITIONAL_PARAMS_FOR_NS).find(data)]
    print root_ns_list
    print "End searching all NS."
    print "---------------------"
    result = dict()
    # 2. walk by list of NS dict for extract pair {pathToNs:NsValue}
    for root_ns_dict in root_ns_list:
        # 3. walk by NS dict for start creating root AP and nested AP for every NS
        for paths, values in root_ns_dict.items():
            print "Start transfiguration for NS by path: %s" % str(paths)
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
                print "---------------------"
                print "\tStart extract>convert>delete VNF..."
                print "\tVNF paths: %s" % str(root_vnf_.keys()[0])
                ext_nested_vnfs = extract_vnfs(root_vnf_.values()[0])
                tmp_root_ap[FOR_RESULT_DOC_NESTED_ADDITIONAL_PARAMS].extend(ext_nested_vnfs)
                delete_child_by_path(data, str(root_vnf_.keys()[0]).split('.'))
                print "\tEnd extract>convert>delete VNF..."
                print "---------------------"
            if nested_nss_ is not None:
                print "---------------------"
                print "\tStart extract>convert>delete nested NS..."
                print "\tNested NS paths: %s" % str(nested_nss_.keys()[0])
                ext_nested_nss = extract_nested_nss(nested_nss_.values()[0])
                tmp_root_ap[FOR_RESULT_DOC_NESTED_ADDITIONAL_PARAMS].extend(ext_nested_nss)
                delete_child_by_path(data, str(nested_nss_.keys()[0]).split('.'))
                print "\tEnd extract>convert>delete nested NS..."
                print "---------------------"

            print "Set key name by path: %s " % str(paths)
            set_value_by_path(data, str(paths).split('.'), tmp_root_ap)

            result.update({paths: tmp_root_ap})
            print "End transfiguration for NS by path: %s" % str(paths)

    print "Result transfiguration: %s" % str(result)
    print "END TRANSFIGURATION."
    print "##########################################################"
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


def by_files(json_path_list):
    for pathToJson in json_path_list:
        print "Start work with json file: " + pathToJson
        with open(pathToJson) as json_file:
            jData = json.load(json_file)
            work_test = transfiguration(jData)
            for path, ap in work_test.items():
                set_key_name_by_path(jData, str(path).split('.'), FOR_RESULT_DOC_ADDITIONAL_PARAMS)

            json_file.seek(0)  # rewind
            json.dump(jData, json_file)
            json_file.truncate()

        print "End work with json file."


def run():
    jsonPathList = find_all_paths_to_json()
    by_files(jsonPathList)

run()
