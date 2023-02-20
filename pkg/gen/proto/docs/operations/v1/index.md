# Protocol Documentation
<a name="top"></a>

## Table of Contents

- [operations/v1/operations.proto](#operations_v1_operations-proto)
    - [CreateBackupRequest](#operations-v1-CreateBackupRequest)
    - [CreateBackupResponse](#operations-v1-CreateBackupResponse)
    - [CreateHypervisorRequest](#operations-v1-CreateHypervisorRequest)
    - [CreateHypervisorResponse](#operations-v1-CreateHypervisorResponse)
    - [DestroyHypervisorRequest](#operations-v1-DestroyHypervisorRequest)
    - [DestroyHypervisorResponse](#operations-v1-DestroyHypervisorResponse)
    - [ExpandStorageRequest](#operations-v1-ExpandStorageRequest)
    - [ExpandStorageResponse](#operations-v1-ExpandStorageResponse)
    - [ListHypervisorsRequest](#operations-v1-ListHypervisorsRequest)
    - [ListHypervisorsResponse](#operations-v1-ListHypervisorsResponse)
    - [ListHypervisorsResponseHypervisor](#operations-v1-ListHypervisorsResponseHypervisor)
    - [ShrinkStorageRequest](#operations-v1-ShrinkStorageRequest)
    - [ShrinkStorageResponse](#operations-v1-ShrinkStorageResponse)
  
    - [HypervisorCapabilities](#operations-v1-HypervisorCapabilities)
    - [HypervisorState](#operations-v1-HypervisorState)
    - [OperationState](#operations-v1-OperationState)
  
    - [OperationsService](#operations-v1-OperationsService)
  
- [Scalar Value Types](#scalar-value-types)



<a name="operations_v1_operations-proto"></a>
<p align="right"><a href="#top">Top</a></p>

## operations/v1/operations.proto



<a name="operations-v1-CreateBackupRequest"></a>

### CreateBackupRequest
CreateBackupRequest is the request for the CreateBackup method






<a name="operations-v1-CreateBackupResponse"></a>

### CreateBackupResponse
CreateBackupResponse is the response for the CreateBackup method


| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| state | [OperationState](#operations-v1-OperationState) |  | state is the state of the operation |
| msg | [string](#string) |  | msg contains info related with the operation |






<a name="operations-v1-CreateHypervisorRequest"></a>

### CreateHypervisorRequest
CreateHypervisorRequest is the request for the CreateHypervisor method


| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| id | [string](#string) |  | id is the ID of the hypervisor |






<a name="operations-v1-CreateHypervisorResponse"></a>

### CreateHypervisorResponse
CreateHypervisorResponse is the response for the CreateHypervisor method


| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| state | [OperationState](#operations-v1-OperationState) |  | state is the state of the operation |
| msg | [string](#string) |  | msg contains info related with the operation |






<a name="operations-v1-DestroyHypervisorRequest"></a>

### DestroyHypervisorRequest
DestroyHypervisorRequest is the request for the DestroyHypervisor method


| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| id | [string](#string) |  | id is the ID of the hypervisor |






<a name="operations-v1-DestroyHypervisorResponse"></a>

### DestroyHypervisorResponse
DestroyHypervisorResponse is the response for the DestroyHypervisor method


| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| state | [OperationState](#operations-v1-OperationState) |  | state is the state of the operation |
| msg | [string](#string) |  | msg contains info related with the operation |






<a name="operations-v1-ExpandStorageRequest"></a>

### ExpandStorageRequest
ExpandStorageRequest is the request for the ExpandStorage method


| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| min_bytes | [int32](#int32) |  | min_bytes is the minimum number of bytes that the storage needs to be expanded |






<a name="operations-v1-ExpandStorageResponse"></a>

### ExpandStorageResponse
ExpandStorageResponse is the response for the ExpandStorage method


| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| state | [OperationState](#operations-v1-OperationState) |  | state is the state of the operation |
| msg | [string](#string) |  | msg contains info related with the operation |






<a name="operations-v1-ListHypervisorsRequest"></a>

### ListHypervisorsRequest
ListHypervisorsRequest is the request for the ListHypervisors method






<a name="operations-v1-ListHypervisorsResponse"></a>

### ListHypervisorsResponse
ListHypervisorsResponse is the response for the ListHypervisors method


| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| hypervisors | [ListHypervisorsResponseHypervisor](#operations-v1-ListHypervisorsResponseHypervisor) | repeated | hypervisors contains all the hypervisors in the operations service |






<a name="operations-v1-ListHypervisorsResponseHypervisor"></a>

### ListHypervisorsResponseHypervisor
ListHypervisorsResponseHypervisor is each hypervisor in the response of the ListHypervisors method


| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| id | [string](#string) |  | id is the ID of the hypervisor |
| cpu | [int32](#int32) |  | cpu is the number of CPU threads that the machine has |
| ram | [int32](#int32) |  | ram is the number of RAM that the machine has. It&#39;s in MB |
| capabilities | [HypervisorCapabilities](#operations-v1-HypervisorCapabilities) | repeated | capabilities are the capabilities that the hypervisor has |
| state | [HypervisorState](#operations-v1-HypervisorState) |  | state is the state of the hypervisor |






<a name="operations-v1-ShrinkStorageRequest"></a>

### ShrinkStorageRequest
ShrinkStorageRequest is the request for the ShrinkStorage method


| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| max_bytes | [int32](#int32) |  | max_bytes is the maximum number of bytes that the storage needs to be shrink |






<a name="operations-v1-ShrinkStorageResponse"></a>

### ShrinkStorageResponse
ShrinkStorageResponse is the response for the ShrinkStorage method


| Field | Type | Label | Description |
| ----- | ---- | ----- | ----------- |
| state | [OperationState](#operations-v1-OperationState) |  | state is the state of the operation |
| msg | [string](#string) |  | msg contains info related with the operation |





 


<a name="operations-v1-HypervisorCapabilities"></a>

### HypervisorCapabilities
HypervisorCapabilites are the different capabilites that a hypervisor can have

| Name | Number | Description |
| ---- | ------ | ----------- |
| HYPERVISOR_CAPABILITIES_UNSPECIFIED | 0 | default zero value |
| HYPERVISOR_CAPABILITIES_STORAGE | 1 | HYPERVISOR_CAPABILITIES_STORAGE means the hypervisor has access to the shared storage pool |
| HYPERVISOR_CAPABILITIES_GPU | 2 | HYPERVISOR_CAPABILITIES_GPU means the hypervisor has access to a GPU |



<a name="operations-v1-HypervisorState"></a>

### HypervisorState
HypervisorState are the different states that a operations hypervisor can be

| Name | Number | Description |
| ---- | ------ | ----------- |
| HYPERVISOR_STATE_UNSPECIFIED | 0 | default zero value |
| HYPERVISOR_STATE_UNKNOWN | 1 | HYPERVISOR_STATE_UNKNOWN |
| HYPERVISOR_STATE_AVAILABLE_TO_CREATE | 2 | HYPERVISOR_STATE_AVAILABLE_TO_CREATE means the hypervisor can be created |
| HYPERVISOR_STATE_AVAILABLE_TO_DESTROY | 3 | HYPERVISOR_STATE_AVAILABLE_TO_DESTROY means the hypervisor can be destroyed |



<a name="operations-v1-OperationState"></a>

### OperationState
OperationState are the different states that a operation can be

| Name | Number | Description |
| ---- | ------ | ----------- |
| OPERATION_STATE_UNSPECIFIED | 0 | default zero value |
| OPERATION_STATE_SCHEDULED | 1 | OPERATION_STATE_SCHEDULED means that the operation is queued, and it&#39;s going to be ran when it&#39;s its time |
| OPERATION_STATE_ACTIVE | 2 | OPERATION_STATE_ACTIVE means that the operation is being executed |
| OPERATION_STATE_FAILED | 3 | OPERATION_STATE_FAILED means the operation has failed |
| OPERATION_STATE_COMPLETED | 4 | OPERATION_STATE_COMPLETED means the operation has finished successfully |


 

 


<a name="operations-v1-OperationsService"></a>

### OperationsService
OperationsService is a service responsible for executing operations in the IsardVDI infrastructure

| Method Name | Request Type | Response Type | Description |
| ----------- | ------------ | ------------- | ------------|
| ListHypervisors | [ListHypervisorsRequest](#operations-v1-ListHypervisorsRequest) | [ListHypervisorsResponse](#operations-v1-ListHypervisorsResponse) | ListHypervisors returns a list with all the hypervisors and their resources |
| CreateHypervisor | [CreateHypervisorRequest](#operations-v1-CreateHypervisorRequest) | [CreateHypervisorResponse](#operations-v1-CreateHypervisorResponse) stream | CreateHypervisor creates and adds a new hypervisor on the pool |
| DestroyHypervisor | [DestroyHypervisorRequest](#operations-v1-DestroyHypervisorRequest) | [DestroyHypervisorResponse](#operations-v1-DestroyHypervisorResponse) stream | DestroyHypervisor destroys a Hypervisor. It doesn&#39;t stop / migrate the running VMs or anything like that |
| ExpandStorage | [ExpandStorageRequest](#operations-v1-ExpandStorageRequest) | [ExpandStorageResponse](#operations-v1-ExpandStorageResponse) stream | ExpandStorage adds more storage to the shared storage pool |
| ShrinkStorage | [ShrinkStorageRequest](#operations-v1-ShrinkStorageRequest) | [ShrinkStorageResponse](#operations-v1-ShrinkStorageResponse) stream | ShrinkStorage removes storage from the shared storage pool |
| CreateBackup | [CreateBackupRequest](#operations-v1-CreateBackupRequest) | [CreateBackupResponse](#operations-v1-CreateBackupResponse) stream | CreateBackup creates a new backup of the storage pool |

 



## Scalar Value Types

| .proto Type | Notes | C++ | Java | Python | Go | C# | PHP | Ruby |
| ----------- | ----- | --- | ---- | ------ | -- | -- | --- | ---- |
| <a name="double" /> double |  | double | double | float | float64 | double | float | Float |
| <a name="float" /> float |  | float | float | float | float32 | float | float | Float |
| <a name="int32" /> int32 | Uses variable-length encoding. Inefficient for encoding negative numbers – if your field is likely to have negative values, use sint32 instead. | int32 | int | int | int32 | int | integer | Bignum or Fixnum (as required) |
| <a name="int64" /> int64 | Uses variable-length encoding. Inefficient for encoding negative numbers – if your field is likely to have negative values, use sint64 instead. | int64 | long | int/long | int64 | long | integer/string | Bignum |
| <a name="uint32" /> uint32 | Uses variable-length encoding. | uint32 | int | int/long | uint32 | uint | integer | Bignum or Fixnum (as required) |
| <a name="uint64" /> uint64 | Uses variable-length encoding. | uint64 | long | int/long | uint64 | ulong | integer/string | Bignum or Fixnum (as required) |
| <a name="sint32" /> sint32 | Uses variable-length encoding. Signed int value. These more efficiently encode negative numbers than regular int32s. | int32 | int | int | int32 | int | integer | Bignum or Fixnum (as required) |
| <a name="sint64" /> sint64 | Uses variable-length encoding. Signed int value. These more efficiently encode negative numbers than regular int64s. | int64 | long | int/long | int64 | long | integer/string | Bignum |
| <a name="fixed32" /> fixed32 | Always four bytes. More efficient than uint32 if values are often greater than 2^28. | uint32 | int | int | uint32 | uint | integer | Bignum or Fixnum (as required) |
| <a name="fixed64" /> fixed64 | Always eight bytes. More efficient than uint64 if values are often greater than 2^56. | uint64 | long | int/long | uint64 | ulong | integer/string | Bignum |
| <a name="sfixed32" /> sfixed32 | Always four bytes. | int32 | int | int | int32 | int | integer | Bignum or Fixnum (as required) |
| <a name="sfixed64" /> sfixed64 | Always eight bytes. | int64 | long | int/long | int64 | long | integer/string | Bignum |
| <a name="bool" /> bool |  | bool | boolean | boolean | bool | bool | boolean | TrueClass/FalseClass |
| <a name="string" /> string | A string must always contain UTF-8 encoded or 7-bit ASCII text. | string | String | str/unicode | string | string | string | String (UTF-8) |
| <a name="bytes" /> bytes | May contain any arbitrary sequence of bytes. | string | ByteString | str | []byte | ByteString | string | String (ASCII-8BIT) |

