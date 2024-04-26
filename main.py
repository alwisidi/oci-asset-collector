# import openpyxl
import json
import logging
import subprocess
import pandas as pd

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.DEBUG)
# log_handler = logging.StreamHandler()
log_handler = logging.FileHandler('my_app.log')
log_handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)7s : %(message)s'))
LOG.addHandler(log_handler)

def oci_command(command):
  return json.loads(subprocess.run(command.split(), capture_output=True, text=True).stdout)

def get_resource(rsc_type, values = []):
  query = 'network vcn list' if rsc_type == 'VCN' else (
    'network subnet list' if rsc_type == 'Subnet' else (
      'network nsg list' if rsc_type == 'NSG' else (
        'compute instance list' if rsc_type == 'Instance' else (
          'bv boot-volume list' if rsc_type == 'Boot Volume' else (
            'compute boot-volume-attachment list' if rsc_type == 'Boot Volume Attachment' else (
              'compute image list' if rsc_type == 'Image' else (
                'compute image get' if rsc_type == 'ImageById' else (
                  'compute instance list-vnics' if rsc_type == 'VNIC' else (
                    'compute vnic-attachment list' if rsc_type == 'VNIC-Attachment' else rsc_type
                  )
                )
              )
            )
          )
        )
      )
    )
  )
  if rsc_type == 'Compartment':
    return [*values, *oci_command(f'oci iam compartment list --include-root --compartment-id-in-subtree true --all')['data']]
  if rsc_type == 'ImageById':
    return oci_command(f"oci {query} --image-id {values}")['data']
  for compartment in OCI.compartments:
    try:
      if rsc_type == "Boot Volume Attachment":
        availability_domains = [domain['name'] for domain in oci_command(f"oci iam availability-domain list --compartment-id {compartment['id']} --all")['data']]
        for domain in availability_domains:
          values = [*values, *oci_command(f"oci {query} --availability-domain {domain} --compartment-id {compartment['id']} --all")['data']]
      else:
        values = [*values, *oci_command(f"oci {query} --compartment-id {compartment['id']} --all")['data']]
      LOG.info(f"[[ {compartment['name']:26s} ]] -> ✅ {rsc_type}s are queried successfully.")
    except (json.JSONDecodeError, KeyError) as e:
      if "Expecting value: line 1 column 1 (char 0)" in str(e):
        LOG.warning(f"[[ {compartment['name']:26s} ]] -> 🔍 No {rsc_type}s found.")
      else:
        LOG.error(e)
  return values

def get_missing_images():
  all_images, current_images = [instance['image-id'] for instance in OCI.instances], [image['id'] for image in OCI.images]
  unique_images = list(set(all_images) - set(current_images))
  LOG.info(f"Unique Images {unique_images.__len__()} -> {unique_images}")
  OCI.images = [*OCI.images, *[get_resource('ImageById', image) for image in unique_images]]
  LOG.info(f"Images added successfully")

def get_value(unique, data_lists, instance_details, matched_values, dest_selectors, called_props):
  try:
    list, dest_selector, called_prop, matches = data_lists.pop(), dest_selectors.pop(), called_props.pop(), []
    if data_lists.__len__() >= 1:
      matched_values = get_value(unique, data_lists, instance_details, matched_values, dest_selectors, called_props)
    def get_matched(item, dest_selector, matched_value, called_prop):
      if item[dest_selector] == matched_value:
        if type(called_prop) is str:
          return item[called_prop]
        else:
          return ' '.join([item[prop] for prop in called_prop])
      else:
        return None
    for item in list:
      if type(matched_values) is str:
        result = get_matched(item, dest_selector, matched_values, called_prop)
        if result is not None:
          matches.append(result if (unique and ('.vnic.' in item['id'] and item['is-primary'] == True)) or not unique or '.vnic.' not in item['id'] else None)
      else:
        for value in matched_values:
          if value is not None:
            result = get_matched(item, dest_selector, value, called_prop)
            if result is not None:
              matches.append(result if (unique and ('.vnic.' in item['id'] and item['is-primary'] == True)) or not unique or '.vnic.' not in item['id'] else None)
    return None if matches.__len__() == 0 else (matches if matches.__len__() > 1 else matches[0])
  except Exception as e:
    LOG.error(f"❗ [[ {instance_details['display-name']} ]] -> {called_prop} -> {e}")
    return None

def aggregator():
  OCI.combined = [{
    'id'                          : instance['id'],
    'region'                      : instance['region'],
    'availability_domain'         : instance['availability-domain'],
    'comparment_name'             : get_value(
      False,
      [OCI.compartments],
      instance,
      instance['compartment-id'],
      ['id'],
      ['name']
    ),
    'server_name'                 : instance['display-name'],
    'status'                      : instance['lifecycle-state'],
    'os_type'                     : get_value(
      False,
      [OCI.images],
      instance,
      instance['image-id'],
      ['id'],
      ['operating-system']
    ),
    'image'                       : get_value(
      False,
      [OCI.images],
      instance,
      instance['image-id'],
      ['id'],
      ['display-name']
    ),
    'fault_domain'                : instance['fault-domain'],
    'primary_vcn'                 : get_value(
      True,
      [OCI.vnic_attachments, OCI.vnics, OCI.subnets, OCI.vcns],
      instance,
      instance['id'],
      ['instance-id', 'id', 'id', 'id'],
      ['vnic-id', 'subnet-id', 'vcn-id', ['display-name', 'cidr-block']]
    ),
    'primary_subnet'              : get_value(
      True,
      [OCI.vnic_attachments, OCI.vnics, OCI.subnets],
      instance,
      instance['id'],
      ['instance-id', 'id', 'id'],
      ['vnic-id', 'subnet-id', ['display-name', 'cidr-block']]
    ),
    # 'specs'       : {
      'shape'                     : instance['shape'],
      'ocpu'                      : instance['shape-config']['ocpus'],
      'memory_gb'                 : instance['shape-config']['memory-in-gbs'],
      'local_storage_gb'          : instance['shape-config']['local-disks-total-size-in-gbs'],
    # },
    'public_ips'                  : get_value(
      False,
      [OCI.vnic_attachments, OCI.vnics],
      instance,
      instance['id'],
      ['instance-id', 'id'],
      ['vnic-id', 'public-ip']
    ),
    'private_ips'                 : get_value(
      False,
      [OCI.vnic_attachments, OCI.vnics],
      instance,
      instance['id'],
      ['instance-id', 'id'],
      ['vnic-id', 'private-ip']
    ),
    'security_groups'             : get_value(
      True,
      [OCI.vnic_attachments, OCI.vnics, OCI.nsgs],
      instance,
      instance['id'],
      ['instance-id', 'id', 'id'],
      ['vnic-id', 'nsg-ids', 'display-name']
    ),
    # 'internal_fqdn'               : None, # Couldn't find it anywhere!!
    'boot_volume'                 : get_value(
      False,
      [OCI.boot_volume_attachments, OCI.boot_volumes],
      instance,
      instance['id'],
      ['instance-id', 'id'],
      ['boot-volume-id', 'display-name']
    ),
    'boot_volume_size_gb'         : get_value(
      False,
      [OCI.boot_volume_attachments, OCI.boot_volumes],
      instance,
      instance['id'],
      ['instance-id', 'id'],
      ['boot-volume-id', 'size-in-gbs']
    ),
    # 'boot_volume_backup_policy'   : '',
    # 'block_volumes'               : '',
    # 'block_volumes_total_gb'      : '',
    # 'block_volumes_backup_policy' : '',
    'freeform_tags'               : instance['freeform-tags'],
    'defined_tags'                : instance['defined-tags'],
    'time_created'                : instance['time-created'],
  } for instance in OCI.instances]

class Asset:
  def __init__(self, compartments, vcns, subnets, nsgs, instances, boot_volumes, boot_volume_attachments, vnics, vnic_attachments, images, combined):
    self.compartments             = compartments
    self.vcns                     = vcns
    self.subnets                  = subnets
    self.nsgs                     = nsgs
    self.instances                = instances
    self.boot_volumes             = boot_volumes
    self.boot_volume_attachments  = boot_volume_attachments
    self.vnics                    = vnics
    self.vnic_attachments         = vnic_attachments
    self.images                   = images
    self.combined                 = combined
  def to_dict(self):
    return {
      "compartments"            : self.compartments,
      "vcns"                    : self.vcns,
      "subnets"                 : self.subnets,
      "nsgs"                    : self.nsgs,
      "instances"               : self.instances,
      "boot_volumes"            : self.boot_volumes,
      "boot_volume_attachments" : self.boot_volume_attachments,
      "vnics"                   : self.vnics,
      "vnic_attachments"        : self.vnic_attachments,
      "images"                  : self.images,
      "combined"                : self.combined
    }
OCI = Asset([], [], [], [], [], [], [], [], [], [], [])

def main(mode = None):
  if mode == "local":
    try:
      with open('data.json', 'r') as file:
        json_data = file.read()
        data = json.loads(json_data)
      if isinstance(data, dict):
        OCI.compartments            = data['compartments']
        OCI.vcns                    = data['vcns']
        OCI.subnets                 = data['subnets']
        OCI.nsgs                    = data['nsgs']
        OCI.instances               = data['instances']
        OCI.boot_volumes            = data['boot_volumes']
        OCI.boot_volume_attachments = data['boot_volume_attachments']
        OCI.images                  = data['images']
        OCI.vnics                   = data['vnics']
        OCI.vnic_attachments        = data['vnic_attachments']
        OCI.combined                = data['combined']
      else:
        print("Unexpected data type in JSON file")
      get_missing_images()
    except FileNotFoundError:
      print("Error: JSON file not found")
    except json.JSONDecodeError:
      print("Error: Invalid JSON format in the file")
  else:
    OCI.compartments            = get_resource("Compartment")
    OCI.vcns                    = get_resource("VCN")
    OCI.subnets                 = get_resource("Subnet")
    OCI.nsgs                    = get_resource("NSG")
    OCI.instances               = get_resource("Instance")
    OCI.boot_volumes            = get_resource('Boot Volume')
    OCI.boot_volume_attachments = get_resource('Boot Volume Attachment')
    OCI.images                  = get_resource("Image")
    OCI.vnics                   = get_resource("VNIC")
    OCI.vnic_attachments        = get_resource("VNIC-Attachment")
    get_missing_images()
  # aggregator()
  try:
    aggregator()
  except Exception as e:
    LOG.error(e)
  with open('data.json', 'w') as file: json.dump(OCI.to_dict(), file)

def export_excel():
  data_frame = pd.DataFrame(tuple(OCI.combined))
  data_frame.to_excel("data.xlsx")

main("online")
export_excel()
