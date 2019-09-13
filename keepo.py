# coding=utf-8
import sys
import os
import json
from glob import glob
from jsonpath_rw import jsonpath, parse

FOR_RESULT_DOC_ADDITIONAL_PARAMS = 'additionalParams'
FOR_RESULT_DOC_NESTED_ADDITIONAL_PARAMS = 'nestedAdditionalParams'
TEMPLATE = 'template'

ADDITIONAL_PARAM = 'additionalParam'
ADDITIONAL_PARAMS_FOR_NS = 'additionalParamForNs'
ADDITIONAL_PARAMS_FOR_VNF = 'additionalParamForVnf'
ADDITIONAL_PARAMS_FOR_NESTED_NS = 'additionalParamForNestedNs'
SAPS = 'saps'

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
    print "End searching. Candidats for transfiguration: \n" + str(json_path_list)
    return json_path_list


def path_converter(path):
    return str(path).replace('[', '').replace(']', '').split('.')


def set_key_name_by_path(data, path, newName):
    if len(path) == 1:
        data.update({newName: data.pop(path[0])})
        return
    if len(path) == 2:
        if type(data) is list:
            idx = int(path[0])
            tmp_obj = data[idx]  # obj under list
            data.pop(idx)
            data.insert(idx, dict({newName: tmp_obj[path[1]]}))
            return
        else:
            data[path[0]].update({newName: data[path[0]].pop(path[1])})
            return
    elif type(data) is list:
        set_key_name_by_path(data[int(path.pop(0))], path, newName)
    else:
        set_key_name_by_path(data[path.pop(0)], path, newName)


def get_value_by_path(data, path):
    if len(path) == 1:
        return data[path[0]]
    elif type(data) is list:
        return get_value_by_path(data[int(path.pop(0))], path)
    else:
        return get_value_by_path(data[path.pop(0)], path)


def set_value_by_path(data, path, target):
    if len(path) == 1:
        data[path[0]] = target
        return
    elif type(data) is list:
        set_value_by_path(data[int(path.pop(0))], path, target)
    else:
        set_value_by_path(data[path.pop(0)], path, target)


def delete_child_by_path(data, path):
    if len(path) == 1:
        data.pop(path[0])
        return
    if len(path) == 2:
        data[path[0]].pop(path[1])
        return
    elif type(data) is list:
        delete_child_by_path(data[int(path.pop(0))], path)
    else:
        delete_child_by_path(data[path.pop(0)], path)


def find_params_for_ns_by_ns_path_lvl(path, entity_list):
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
    if data is not None:
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
    if data is not None:
        for item in data:
            nested_nss.append(create_nested_ns(item))
    return nested_nss


def check_invalid_json(data):
    inv_path = 'instantiateNses'
    inv_result = [match.full_path for match in parse('$..%s' % inv_path).find(data)]
    if len(inv_result) > 0:
        return True
    return False


# find all NS -> [0:n] transf into root FOR_RESULT_DOC_ADDITIONAL_PARAMS >
# > find all VNF for cur NS by path (relative NS and VNF state by once lvl) >
# > added VNF into FOR_RESULT_DOC_NESTED_ADDITIONAL_PARAMS >
# > find Nested NS and repeat operation as for NS
def transfiguration(data):
    # 1. find all NS:
    if check_invalid_json(data):
        return dict()
    print "---------------------"
    print "START TRANSFIGURATION..."
    result = dict()
    root_ns_list = [{match.full_path: match.value} for match in parse('$..%s' % ADDITIONAL_PARAMS_FOR_NS).find(data)]
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
            root_vnf_ = find_params_for_ns_by_ns_path_lvl(paths, root_vnf_list)

            # 6. find nested NS AP
            nested_nss_list = [{match.full_path: match.value} for match in
                               parse('$..%s' % ADDITIONAL_PARAMS_FOR_NESTED_NS).find(data)]
            # 7. extract nested NS AP which are only at the NS level
            nested_nss_ = find_params_for_ns_by_ns_path_lvl(paths, nested_nss_list)
            # 8. create nested params for nns and vnf && fill nested ap && delete nns and vnf from source json
            if root_vnf_ is not None:
                print "\tFound VNF paths: %s" % str(root_vnf_.keys()[0])
                ext_nested_vnfs = extract_vnfs(root_vnf_.values()[0])
                tmp_root_ap[FOR_RESULT_DOC_NESTED_ADDITIONAL_PARAMS].extend(ext_nested_vnfs)
                tmp_path_vnf = path_converter(root_vnf_.keys()[0])
                delete_child_by_path(data, tmp_path_vnf)

            if nested_nss_ is not None:
                print "\tFound Nested NS paths: %s" % str(nested_nss_.keys()[0])
                ext_nested_nss = extract_nested_nss(nested_nss_.values()[0])
                tmp_root_ap[FOR_RESULT_DOC_NESTED_ADDITIONAL_PARAMS].extend(ext_nested_nss)
                tmp_path_nss = path_converter(nested_nss_.keys()[0])
                delete_child_by_path(data, tmp_path_nss)

            # 9. take SAPSs
            root_saps_list = [{match.full_path: match.value} for match in parse('$..%s' % SAPS).find(data)]
            root_saps_ = find_params_for_ns_by_ns_path_lvl(paths, root_saps_list)
            if root_saps_ is not None:
                print "\t Found SAPSs: %s" % str(root_saps_.keys())
                tmp_path_saps = path_converter(root_saps_.keys()[0])
                tmp_saps_value = get_value_by_path(data, tmp_path_saps)
                tmp_root_ap.update({SAPS: tmp_saps_value})
                tmp_path_saps = path_converter(root_saps_.keys()[0])
                delete_child_by_path(data, tmp_path_saps)

            # 10. change name
            print "Set key name %s on %s" % (ADDITIONAL_PARAMS_FOR_NS, FOR_RESULT_DOC_ADDITIONAL_PARAMS)
            tmp_path_ns = str(paths).replace('[', '').replace(']', '').split('.')
            set_value_by_path(data, tmp_path_ns, tmp_root_ap)

            result.update({paths: tmp_root_ap})
            print "End transfiguration for NS by path: %s" % str(paths)

    print "Result transfiguration: \n%s" % str(result)
    print "END TRANSFIGURATION."
    print "##########################################################"
    return result


def by_files(json_path_list):
    for pathToJson in json_path_list:
        print "Start work with json file: " + pathToJson
        with open(pathToJson, 'r+') as json_file:
            jData = json.load(json_file)
            work_test = transfiguration(jData)
            for path, ap in work_test.items():
                tmp_path = path_converter(path)
                set_key_name_by_path(jData, tmp_path, FOR_RESULT_DOC_ADDITIONAL_PARAMS)
            json_file.seek(0)
            json.dump(jData, json_file)
            json_file.truncate()

        print "End work with json file."
# str
def get_json_names_from_argv():
    jnl = list()
    for item in sys.argv:
        if item.find('.json') > 0:
            jnl.append(item)
    return jnl

def run():
    if len(sys.argv) > 1:
        # find path to files ?
        by_files(get_json_names_from_argv())
    else:
        jsonPathList = find_all_paths_to_json()
        by_files(jsonPathList)


run()