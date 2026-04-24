# APIv4 audit report

Total endpoints probed: **314**

## Status summary

- **2xx**: 188
- **4xx (400)**: 54
- **4xx (403)**: 3
- **4xx (404)**: 64
- **4xx (409)**: 3
- **4xx (428)**: 2

## Failures by signature

### HTTP400 @ <unknown>: Request body must be JSON  (20 hits)

- `POST /api/v4/admin/bulk/user` → HTTP 400
- `POST /api/v4/admin/domains/xml_sections/parse` → HTTP 400
- `POST /api/v4/admin/domains/xml_sections/{domain_id}` → HTTP 400
- `POST /api/v4/admin/domains/xml_sections/{domain_id}/save_virt_install` → HTTP 400
- `PUT /api/v4/admin/hypervisor/{hyper_id}/boot_progress` → HTTP 400
- `PUT /api/v4/admin/limits/category/{category_id}` → HTTP 400
- `PUT /api/v4/admin/limits/group/{group_id}` → HTTP 400
- `PUT /api/v4/admin/notify/desktops/queue/{hyp_id}` → HTTP 400
- `PUT /api/v4/admin/quota/category/{category_id}` → HTTP 400
- `PUT /api/v4/admin/quota/group/{group_id}` → HTTP 400
- `PUT /api/v4/admin/role/{role_id}` → HTTP 400
- `POST /api/v4/admin/socketio` → HTTP 400
- `POST /api/v4/admin/user/auto-register` → HTTP 400
- `PUT /api/v4/admin/users/bulk` → HTTP 400
- `POST /api/v4/admin/users/csv` → HTTP 400
- `POST /api/v4/admin/users/csv/validate` → HTTP 400
- `PUT /api/v4/admin/users/csv/validate` → HTTP 400
- `POST /api/v4/admin/virt_install/xml_sections/{virt_id}` → HTTP 400
- `POST /api/v4/admin/vlans` → HTTP 400
- `DELETE /api/v4/admin/vpn_connections` → HTTP 400

### HTTP404 @ <unknown>: Authentication policy default not found  (5 hits)

- `PUT /api/v4/admin/authentication/force_validate/disclaimer/{policy_id}` → HTTP 404
- `PUT /api/v4/admin/authentication/force_validate/email/{policy_id}` → HTTP 404
- `PUT /api/v4/admin/authentication/force_validate/password/{policy_id}` → HTTP 404
- `DELETE /api/v4/admin/authentication/policy/{policy_id}` → HTTP 404
- `GET /api/v4/admin/authentication/policy/{policy_id}` → HTTP 404

### HTTP404 @ <unknown>: Document with id <UUID> does not exist.  (5 hits)

- `GET /api/v4/admin/category/{category_id}/authentication` → HTTP 404
- `PUT /api/v4/admin/category/{category_id}/authentication` → HTTP 404
- `GET /api/v4/admin/category/{category_id}/branding` → HTTP 404
- `PUT /api/v4/admin/category/{category_id}/branding` → HTTP 404
- `PUT /api/v4/admin/category/{category_id}/login_notification` → HTTP 404

### HTTP404 @ <unknown>: Domain <UUID> not found  (5 hits)

- `GET /api/v4/admin/domain/search-info/{domain_id}` → HTTP 404
- `GET /api/v4/admin/domain/{domain_id}/details` → HTTP 404
- `GET /api/v4/admin/domain/{domain_id}/viewer_data` → HTTP 404
- `GET /api/v4/admin/domain/{domain_id}/xml` → HTTP 404
- `POST /api/v4/admin/domain/{domain_id}/xml` → HTTP 404

### HTTP404 @ <unknown>: Storage x not found  (4 hits)

- `GET /api/v4/admin/storage/domains/{storage_id}` → HTTP 404
- `GET /api/v4/admin/storage/info/{storage_id}` → HTTP 404
- `GET /api/v4/admin/storage/search-info/{storage_id}` → HTTP 404
- `DELETE /api/v4/admin/storage/{storage_id}` → HTTP 404

### HTTP404 @ <unknown>: Hypervisor isard-hypervisor not found  (3 hits)

- `GET /api/v4/admin/hypervisor/status/{hyper_id}` → HTTP 404
- `GET /api/v4/admin/hypervisor/{hyper_id}/virt_pools` → HTTP 404
- `PUT /api/v4/admin/hypervisor/{hyper_id}/virt_pools` → HTTP 404

### HTTP403 @ <unknown>: Operations API is not enabled  (3 hits)

- `DELETE /api/v4/admin/operations/hypervisor/{hypervisor_id}` → HTTP 403
- `PUT /api/v4/admin/operations/hypervisor/{hypervisor_id}` → HTTP 403
- `GET /api/v4/admin/operations/hypervisors` → HTTP 403

### HTTP404 @ <unknown>: Hypervisor with ID x does not exist.  (3 hits)

- `GET /api/v4/admin/orchestrator/hypervisor/{hypervisor_id}` → HTTP 404
- `DELETE /api/v4/admin/orchestrator/hypervisor/{hypervisor_id}/dead_row` → HTTP 404
- `POST /api/v4/admin/orchestrator/hypervisor/{hypervisor_id}/dead_row` → HTTP 404

### HTTP404 @ <unknown>: Active client vpn connection: Vpn kind domains not found  (3 hits)

- `DELETE /api/v4/admin/vpn_connection/{kind}/{client_ip}` → HTTP 404
- `POST /api/v4/admin/vpn_connection/{kind}/{client_ip}` → HTTP 404
- `PUT /api/v4/admin/vpn_connection/{kind}/{client_ip}` → HTTP 404

### HTTP404 @ <unknown>: Template <UUID> not found  (2 hits)

- `GET /api/v4/admin/desktops/tree_list/{template_id}` → HTTP 404
- `DELETE /api/v4/admin/templates/delete/{template_id}` → HTTP 404

### HTTP400 @ <unknown>: Request body must be JSON or multipart form data  (2 hits)

- `POST /api/v4/admin/logs_desktops` → HTTP 400
- `POST /api/v4/admin/logs_users` → HTTP 400

### HTTP400 @ <unknown>: Request body must be multipart form data  (2 hits)

- `POST /api/v4/admin/logs_desktops/{view}` → HTTP 400
- `POST /api/v4/admin/logs_users/{view}` → HTTP 400

### ValidationError @ <schema>: body: Field required  (2 hits)

- `DELETE /api/v4/admin/notification/{notification_id}` → HTTP 400
- `DELETE /api/v4/admin/queues/old_tasks` → HTTP 400

### HTTP400 @ <unknown>: Unknown quota kind 'domains'  (2 hits)

- `GET /api/v4/admin/quota/{kind}` → HTTP 400
- `GET /api/v4/admin/quota/{kind}/{item_id}` → HTTP 400

### HTTP400 @ <unknown>: Missing 'id' field in request body  (2 hits)

- `POST /api/v4/admin/table/add/{table}` → HTTP 400
- `PUT /api/v4/admin/table/update/{table}` → HTTP 400

### HTTP400 @ <unknown>: start_date and end_date are required (YYYY-MM-DD)  (2 hits)

- `PUT /api/v4/admin/usage` → HTTP 400
- `PUT /api/v4/admin/usage/start_end` → HTTP 400

### HTTP404 @ <unknown>: Category credit ID not found in database  (2 hits)

- `GET /api/v4/admin/usage/category_credits/{category_credit_id}` → HTTP 404
- `GET /api/v4/admin/usage/check/overlapping/{credit_id}/{start_date}/{end_date}` → HTTP 404

### HTTP400 @ <unknown>: Invalid start_date 'x': expected YYYY-MM-DD  (2 hits)

- `GET /api/v4/admin/usage/credits/{consumer}/{item_type}/{item_id}/{grouping_id}/{start_date}/{end_date}` → HTTP 400
- `GET /api/v4/admin/usage/distinct_items/{item_consumer}/{start}/{end}` → HTTP 400

### HTTP400 @ <unknown>: Expected maximum must be greater than the expected minimum  (2 hits)

- `POST /api/v4/admin/usage/limits` → HTTP 400
- `PUT /api/v4/admin/usage/limits/{limit_id}` → HTTP 400

### HTTP404 @ <unknown>: Desktop with ID <UUID> not found  (2 hits)

- `GET /api/v4/item/desktop/{desktop_id}` → HTTP 404
- `GET /api/v4/item/desktop/{desktop_id}/get-details` → HTTP 404

### HTTP404 @ <unknown>: Backup not found  (1 hits)

- `GET /api/v4/admin/backups/{backup_id}` → HTTP 404

### HTTP409 @ <unknown>: Item with this name: e2e_real_w0_1776256342_c already exists in categories  (1 hits)

- `POST /api/v4/admin/category` → HTTP 409

### HTTP404 @ <unknown>: Category x not found  (1 hits)

- `GET /api/v4/admin/category/get/{category_name}` → HTTP 404

### HTTP404 @ <unknown>: Category <UUID> not found  (1 hits)

- `GET /api/v4/admin/category/{category_id}` → HTTP 404

### HTTP428 @ <unknown>: DNS record for "_isardvdi-bastion-category.e2e_real_w0_1776256342_x" not foun...  (1 hits)

- `PUT /api/v4/admin/category/{category_id}/bastion_domain` → HTTP 428

### ValidationError @ <schema>: path.notification_type: Input should be 'cover' or 'form'  (1 hits)

- `PUT /api/v4/admin/category/{category_id}/login_notification/{notification_type}/enable` → HTTP 400

### HTTP404 @ <unknown>: Deployment <UUID> not found  (1 hits)

- `GET /api/v4/admin/deployment/{deployment_id}/viewer_data` → HTTP 404

### HTTP400 @ <unknown>: Unknown echart view: x  (1 hits)

- `POST /api/v4/admin/echart/{view}` → HTTP 400

### HTTP409 @ <unknown>: Item with this name: e2e_real_w0_1776256342_g already exists in groups  (1 hits)

- `POST /api/v4/admin/group` → HTTP 409

### HTTP404 @ <unknown>: Group e2e_real_w0_1776256342_x not found  (1 hits)

- `POST /api/v4/admin/group/enrollment` → HTTP 404

### HTTP404 @ <unknown>: Not found group name x  (1 hits)

- `GET /api/v4/admin/group/get/{category_name}/{group_name}` → HTTP 404

### HTTP404 @ <unknown>: Not found group_id <UUID>  (1 hits)

- `GET /api/v4/admin/group/{group_id}` → HTTP 404

### HTTP400 @ <unknown>: DNS resolution failed for e2e_real_w0_1776256342_x  (1 hits)

- `POST /api/v4/admin/hypervisor` → HTTP 400

### HTTP404 @ <unknown>: Mountpoints information still not available  (1 hits)

- `GET /api/v4/admin/hypervisor/mountpoints/{hyper_id}` → HTTP 404

### HTTP404 @ <unknown>: Domain with mac e2e_real_w0_1776256342_x not found in wireguard cache  (1 hits)

- `POST /api/v4/admin/hypervisor/vm/wg_addr` → HTTP 404

### HTTP400 @ <unknown>: Hypervisor update bad data  (1 hits)

- `PUT /api/v4/admin/hypervisor/{hyper_id}` → HTTP 400

### HTTP404 @ <unknown>: Hypervisor not found for id isard-hypervisor  (1 hits)

- `GET /api/v4/admin/hypervisor_vpn/{hyper_id}` → HTTP 404

### HTTP400 @ <unknown>: Hypervisor status incorrect  (1 hits)

- `GET /api/v4/admin/hypervisors/{status}` → HTTP 400

### HTTP404 @ <unknown>: No migration found when deleting  (1 hits)

- `DELETE /api/v4/admin/migrations/{migration_id}` → HTTP 404

### HTTP404 @ <unknown>: Migration x not found  (1 hits)

- `PUT /api/v4/admin/migrations/{migration_id}/revoke` → HTTP 404

### HTTP400 @ <unknown>: Template must include 'default' and matching 'lang' entry  (1 hits)

- `POST /api/v4/admin/notifications/template` → HTTP 400

### HTTP404 @ <unknown>: Unknown notification event: e2e_real_w0_1776256342_x  (1 hits)

- `PUT /api/v4/admin/notifications/template/preview` → HTTP 404

### HTTP404 @ <unknown>: Notification template <UUID> not found  (1 hits)

- `DELETE /api/v4/admin/notifications/template/{template_id}` → HTTP 404

### HTTP404 @ <unknown>: Notification template with ID: <UUID> not found  (1 hits)

- `GET /api/v4/admin/notifications/template/{template_id}` → HTTP 404

### ValidationError @ <schema>: path.older_than: Input should be a valid integer, unable to parse string as a...  (1 hits)

- `GET /api/v4/admin/queues/old_tasks/{older_than}` → HTTP 400

### HTTP400 @ <unknown>: Unknown reservable type: x  (1 hits)

- `PUT /api/v4/admin/reservables/{reservable_type}/{item_id}` → HTTP 400

### HTTP404 @ <unknown>: Role not found  (1 hits)

- `GET /api/v4/admin/role/{role_id}` → HTTP 404

### HTTP404 @ <unknown>: Category e2e_real_w0_1776256342_x not found  (1 hits)

- `POST /api/v4/admin/secret` → HTTP 404

### HTTP404 @ <unknown>: Item <UUID> not found  (1 hits)

- `DELETE /api/v4/admin/secret/{kid}` → HTTP 404

### HTTP400 @ <unknown>: Invalid role: x. Valid roles are: admin, manager, advanced, user  (1 hits)

- `GET /api/v4/admin/storage/by-role/{role}` → HTTP 400

### HTTP404 @ <unknown>: Item default not found  (1 hits)

- `DELETE /api/v4/admin/table/{table}/{item_id}` → HTTP 404

### HTTP404 @ <unknown>: Task not found  (1 hits)

- `PUT /api/v4/admin/task/{task_id}/retry` → HTTP 404

### HTTP400 @ <unknown>: Item type x not valid for consumption calculation  (1 hits)

- `PUT /api/v4/admin/usage/consolidate/{item_type}` → HTTP 400

### ValidationError @ <schema>: path.days: Input should be a valid integer, unable to parse string as an integer  (1 hits)

- `PUT /api/v4/admin/usage/consolidate/{item_type}/{days}` → HTTP 400

### HTTP400 @ <unknown>: Invalid start_date 'e2e_real_w0_1776256342_x': expected YYYY-MM-DD  (1 hits)

- `POST /api/v4/admin/usage/credits` → HTTP 400

### HTTP404 @ <unknown>: Credit with ID x not found in database  (1 hits)

- `DELETE /api/v4/admin/usage/credits/{credit_id}` → HTTP 404

### HTTP404 @ <unknown>: Usage credit not found  (1 hits)

- `PUT /api/v4/admin/usage/credits/{credit_id}` → HTTP 404

### HTTP404 @ <unknown>: Grouping not found  (1 hits)

- `GET /api/v4/admin/usage/grouping/{grouping_id}` → HTTP 404

### HTTP404 @ <unknown>: Parameter grouping with ID x not found in database  (1 hits)

- `DELETE /api/v4/admin/usage/groupings/{grouping_id}` → HTTP 404

### HTTP404 @ <unknown>: Limit with ID x not found in database  (1 hits)

- `DELETE /api/v4/admin/usage/limits/{limit_id}` → HTTP 404

### HTTP404 @ <unknown>: Parameter with ID x not found in database  (1 hits)

- `DELETE /api/v4/admin/usage/parameters/{parameter_id}` → HTTP 404

### HTTP400 @ <unknown>: Invalid date: expected YYYY-MM-DD  (1 hits)

- `GET /api/v4/admin/usage/reset_date/{start_date}/{end_date}` → HTTP 400

### HTTP404 @ <unknown>: No consumption data for item default  (1 hits)

- `PUT /api/v4/admin/usage/unify/{item_id}/item_name` → HTTP 404

### HTTP409 @ <unknown>: User with uid e2e_real_w0_1776256342_u already exists in category default for...  (1 hits)

- `POST /api/v4/admin/user` → HTTP 409

### HTTP404 @ <unknown>: No verified user with email x in category x  (1 hits)

- `GET /api/v4/admin/user/email-category/{email}/{category}` → HTTP 404

### HTTP400 @ <unknown>: UserVpn: no OS supplied  (1 hits)

- `GET /api/v4/admin/user/{user_id}/vpn/{kind}` → HTTP 400

### HTTP400 @ <unknown>: Unknown VPN kind 'domains'; expected one of: config, install  (1 hits)

- `GET /api/v4/admin/user/{user_id}/vpn/{kind}/{os}` → HTTP 400

### HTTP400 @ <unknown>: Auth protocol 'x' is not supported  (1 hits)

- `POST /api/v4/admin/user_storage/new/{auth_protocol}` → HTTP 400

### HTTP404 @ <unknown>: User e2e_real_w0_1776256342_x not found  (1 hits)

- `PUT /api/v4/admin/users/reset-password` → HTTP 404

### HTTP400 @ <unknown>: Invalid viewer value to reset  (1 hits)

- `PUT /api/v4/admin/viewers-config/reset/{viewer}` → HTTP 400

### HTTP404 @ <unknown>: virt_install x not found  (1 hits)

- `GET /api/v4/admin/virt_install/xml_sections/{virt_id}` → HTTP 404

### HTTP400 @ <unknown>: Unsupported reset kind 'domains'; expected 'all'  (1 hits)

- `DELETE /api/v4/admin/vpn_connection/{kind}` → HTTP 400

### HTTP428 @ <unknown>: No hypervisors available for category default with storage pool <UUID>  (1 hits)

- `GET /api/v4/storage-pool/availability` → HTTP 428

<details><summary>Passing endpoints (188)</summary>

- `POST /api/v4/admin/allowed/term/{table}` → 200
- `POST /api/v4/admin/allowed/update/{table}` → 200
- `GET /api/v4/admin/authentication/policies` → 200
- `POST /api/v4/admin/authentication/policy` → 200
- `PUT /api/v4/admin/authentication/policy/{policy_id}` → 200
- `GET /api/v4/admin/authentication/providers` → 200
- `GET /api/v4/admin/backups` → 200
- `GET /api/v4/admin/backups/config` → 200
- `GET /api/v4/admin/categories` → 200
- `GET /api/v4/admin/categories/{frontend}` → 200
- `POST /api/v4/admin/category/delete/check` → 200
- `DELETE /api/v4/admin/category/{category_id}` → 200
- `PUT /api/v4/admin/category/{category_id}` → 200
- `GET /api/v4/admin/category/{category_id}/bastion_domain` → 200
- `GET /api/v4/admin/category/{category_id}/users` → 200
- `POST /api/v4/admin/check/group/category` → 200
- `GET /api/v4/admin/config/user-migration` → 200
- `PUT /api/v4/admin/config/user-migration` → 200
- `GET /api/v4/admin/domain/storage/{domain_id}` → 200
- `GET /api/v4/admin/domain/template_tree/{desktop_id}` → 200
- `POST /api/v4/admin/domains` → 200
- `GET /api/v4/admin/domains/started-count` → 200
- `PUT /api/v4/admin/domains/status/{status}/find_storages` → 200
- `GET /api/v4/admin/domains/xml_capabilities` → 200
- `GET /api/v4/admin/domains/xml_sections/{domain_id}` → 200
- `GET /api/v4/admin/domains/{field}/{kind}` → 200
- `GET /api/v4/admin/domains_status/{status}` → 200
- `GET /api/v4/admin/downloads` → 200
- `POST /api/v4/admin/downloads/register` → 200
- `POST /api/v4/admin/downloads/{action}/{kind}` → 200
- `POST /api/v4/admin/downloads/{action}/{kind}/{id}` → 200
- `GET /api/v4/admin/downloads/{kind}` → 200
- `POST /api/v4/admin/group/delete/check` → 200
- `DELETE /api/v4/admin/group/{group_id}` → 200
- `PUT /api/v4/admin/group/{group_id}` → 200
- `GET /api/v4/admin/group/{group_id}/users` → 200
- `GET /api/v4/admin/groups` → 200
- `POST /api/v4/admin/hypervisor/disks_found` → 200
- `POST /api/v4/admin/hypervisor/media_delete` → 200
- `POST /api/v4/admin/hypervisor/media_found` → 200
- `GET /api/v4/admin/hypervisor/started_domains/{hyper_id}` → 200
- `PUT /api/v4/admin/hypervisor/stop/{hyper_id}` → 200
- `DELETE /api/v4/admin/hypervisor/{hyper_id}` → 200
- `GET /api/v4/admin/hypervisors` → 200
- `PUT /api/v4/admin/hypervisors/gpus` → 200
- `POST /api/v4/admin/hypervisors/orchestrator_managed` → 200
- `POST /api/v4/admin/images/desktops/generate` → 200
- `GET /api/v4/admin/items/desktops` → 200
- `GET /api/v4/admin/items/templates` → 200
- `GET /api/v4/admin/jwt/{user_id}` → 200
- `GET /api/v4/admin/logs_desktops/list` → 200
- `GET /api/v4/admin/logs_users/list` → 200
- `GET /api/v4/admin/media` → 200
- `GET /api/v4/admin/media/domains/{storage_id}` → 200
- `GET /api/v4/admin/media/{status}` → 200
- `GET /api/v4/admin/migrations` → 200
- `POST /api/v4/admin/multiple_actions` → 200
- `POST /api/v4/admin/notification` → 200
- `GET /api/v4/admin/notification/actions` → 200
- `GET /api/v4/admin/notification/{notification_id}` → 200
- `PUT /api/v4/admin/notification/{notification_id}` → 200
- `GET /api/v4/admin/notifications` → 200
- `DELETE /api/v4/admin/notifications/data` → 200
- `GET /api/v4/admin/notifications/data/by_status/{status}` → 200
- `GET /api/v4/admin/notifications/data/status/{status}/user/{user_id}` → 200
- `DELETE /api/v4/admin/notifications/data/user/{user_id}` → 200
- `DELETE /api/v4/admin/notifications/data/{notification_data_id}` → 200
- `GET /api/v4/admin/notifications/statuses` → 200
- `PUT /api/v4/admin/notifications/template/{template_id}` → 200
- `GET /api/v4/admin/notifications/templates` → 200
- `GET /api/v4/admin/notifications/templates/custom` → 200
- `GET /api/v4/admin/notifications/templates/system` → 200
- `GET /api/v4/admin/notifications/user/displays/{user_id}/{trigger}` → 200
- `POST /api/v4/admin/notify/desktop` → 200
- `POST /api/v4/admin/notify/user/desktop` → 200
- `DELETE /api/v4/admin/orchestrator/hypervisor/{hypervisor_id}/desktops` → 200
- `DELETE /api/v4/admin/orchestrator/hypervisor/{hypervisor_id}/manage` → 200
- `POST /api/v4/admin/orchestrator/hypervisor/{hypervisor_id}/manage` → 200
- `GET /api/v4/admin/orchestrator/hypervisors` → 200
- `GET /api/v4/admin/queues` → 200
- `GET /api/v4/admin/queues/consumers` → 200
- `DELETE /api/v4/admin/queues/old_tasks/auto` → 200
- `GET /api/v4/admin/queues/old_tasks/config` → 200
- `PUT /api/v4/admin/queues/old_tasks/config/enabled` → 200
- `PUT /api/v4/admin/queues/old_tasks/config/max_time/{max_time}` → 200
- `PUT /api/v4/admin/queues/old_tasks/config/queue_registries` → 200
- `GET /api/v4/admin/quotas` → 200
- `GET /api/v4/admin/roles` → 200
- `GET /api/v4/admin/scheduler/jobs/bookings` → 200
- `GET /api/v4/admin/scheduler/jobs/system` → 200
- `GET /api/v4/admin/secrets` → 200
- `POST /api/v4/admin/socketio/broadcast` → 200
- `GET /api/v4/admin/storage` → 200
- `POST /api/v4/admin/storage` → 200
- `GET /api/v4/admin/storage/by-status/{status}` → 200
- `POST /api/v4/admin/storage/by-status/{status}` → 200
- `GET /api/v4/admin/table/{table}` → 200
- `POST /api/v4/admin/table/{table}` → 200
- `GET /api/v4/admin/tasks` → 200
- `PUT /api/v4/admin/tasks/retry` → 200
- `GET /api/v4/admin/templates` → 200
- `GET /api/v4/admin/usage/category_credits` → 200
- `PUT /api/v4/admin/usage/consolidate` → 200
- `GET /api/v4/admin/usage/consumers` → 200
- `GET /api/v4/admin/usage/consumers/{item_type}` → 200
- `DELETE /api/v4/admin/usage/delete_data` → 200
- `GET /api/v4/admin/usage/groupings` → 200
- `POST /api/v4/admin/usage/groupings` → 200
- `PUT /api/v4/admin/usage/groupings/{grouping_id}` → 200
- `GET /api/v4/admin/usage/groupings_dropdown` → 200
- `GET /api/v4/admin/usage/limits` → 200
- `PUT /api/v4/admin/usage/list_parameters` → 200
- `GET /api/v4/admin/usage/parameters` → 200
- `POST /api/v4/admin/usage/parameters` → 200
- `PUT /api/v4/admin/usage/parameters/{parameter_id}` → 200
- `GET /api/v4/admin/usage/reset_date` → 200
- `PUT /api/v4/admin/usage/reset_dates` → 200
- `DELETE /api/v4/admin/user` → 200
- `GET /api/v4/admin/user/appliedquota/{user_id}` → 200
- `POST /api/v4/admin/user/check/migrated` → 200
- `POST /api/v4/admin/user/delete/check` → 200
- `GET /api/v4/admin/user/migrate/check/{user_id}/{target_user_id}` → 200
- `PUT /api/v4/admin/user/migrate/resource/deployments/{user_id}/{target_user_id}` → 200
- `PUT /api/v4/admin/user/migrate/resource/desktop/{user_id}/{target_user_id}` → 200
- `PUT /api/v4/admin/user/migrate/resource/media/{user_id}/{target_user_id}` → 200
- `PUT /api/v4/admin/user/migrate/resource/template/{user_id}/{target_user_id}` → 200
- `PUT /api/v4/admin/user/migrate/{user_id}/{target_user_id}` → 200
- `GET /api/v4/admin/user/password-policy/{user_id}` → 200
- `GET /api/v4/admin/user/required/disclaimer-acknowledgement/{user_id}` → 200
- `GET /api/v4/admin/user/required/email-verification/{user_id}` → 200
- `GET /api/v4/admin/user/required/password-reset/{user_id}` → 200
- `PUT /api/v4/admin/user/reset-vpn/{user_id}` → 200
- `PUT /api/v4/admin/user/secondary-groups/add` → 200
- `PUT /api/v4/admin/user/secondary-groups/delete` → 200
- `PUT /api/v4/admin/user/secondary-groups/overwrite` → 200
- `GET /api/v4/admin/user/{user_id}` → 200
- `PUT /api/v4/admin/user/{user_id}` → 200
- `GET /api/v4/admin/user/{user_id}/desktops` → 200
- `GET /api/v4/admin/user/{user_id}/exists` → 200
- `PUT /api/v4/admin/user/{user_id}/logout` → 200
- `GET /api/v4/admin/user/{user_id}/raw` → 200
- `GET /api/v4/admin/user/{user_id}/templates` → 200
- `GET /api/v4/admin/user_storage` → 200
- `POST /api/v4/admin/user_storage/auto_register` → 200
- `POST /api/v4/admin/user_storage/conn_test` → 200
- `DELETE /api/v4/admin/user_storage/reset/all` → 200
- `GET /api/v4/admin/user_storage/users` → 200
- `DELETE /api/v4/admin/user_storage/{provider_id}` → 200
- `GET /api/v4/admin/user_storage/{provider_id}` → 200
- `DELETE /api/v4/admin/user_storage/{provider_id}/reset` → 200
- `PUT /api/v4/admin/user_storage/{provider_id}/sync/{item}` → 200
- `GET /api/v4/admin/users` → 200
- `PUT /api/v4/admin/users/csv` → 200
- `POST /api/v4/admin/users/search` → 200
- `GET /api/v4/admin/users/{nav}/categories` → 200
- `GET /api/v4/admin/users/{nav}/groups` → 200
- `GET /api/v4/admin/users/{nav}/users` → 200
- `GET /api/v4/admin/userschema` → 200
- `GET /api/v4/admin/viewers-config` → 200
- `PUT /api/v4/admin/viewers-config/{viewer}` → 200
- `GET /api/v4/bastion/config` → 200
- `GET /api/v4/item/login-config` → 200
- `GET /api/v4/item/recycle-bin/count` → 200
- `GET /api/v4/item/recycle-bin/get-default-delete-config` → 200
- `GET /api/v4/item/recycle-bin/get-user-cutoff-time` → 200
- `GET /api/v4/item/user/desktops` → 200
- `GET /api/v4/item/user/get-allowed-hardware` → 200
- `GET /api/v4/item/user/get-config` → 200
- `GET /api/v4/item/user/get-details` → 200
- `GET /api/v4/item/user/get-quotas` → 200
- `GET /api/v4/item/user/webapp-desktops` → 200
- `GET /api/v4/item/user/webapp-templates` → 200
- `GET /api/v4/items/bookings/all` → 200
- `GET /api/v4/items/categories` → 200
- `GET /api/v4/items/media` → 200
- `GET /api/v4/items/media/get-allowed` → 200
- `GET /api/v4/items/media/get-shared` → 200
- `GET /api/v4/items/media/installs` → 200
- `GET /api/v4/items/templates` → 200
- `GET /api/v4/items/templates/get-allowed` → 200
- `GET /api/v4/items/templates/get-shared` → 200
- `GET /api/v4/media/status` → 200
- `GET /api/v4/notifications/status-bar` → 200
- `GET /api/v4/quota/media/new` → 204
- `GET /api/v4/stats/categories` → 200
- `GET /api/v4/stats/categories/deployments` → 200
- `GET /api/v4/stats/desktops/status` → 200
- `GET /api/v4/stats/domains/status` → 200

</details>
