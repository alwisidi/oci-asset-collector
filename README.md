# OCI Asset Collector
This Python script aggregates information about various resources in an Oracle Cloud Infrastructure (OCI) tenancy. It can be run in two modes:

* **Online**: Queries OCI directly to retrieve resource information.
* **Local**: Loads resource data from a pre-existing JSON file (data.json).

## Prerequisites
* **Python v3** with required library:
```bash
pip install pandas
```
* **oci-cli** (OCI Python SDK - installation instructions can be found on the [OCI documentation website][oci-doc])
* An OCI configuration file set up with your OCI credentials.

[oci-doc]: <https://docs.oracle.com/en-us/iaas/Content/API/SDKDocs/cliinstall.htm>
