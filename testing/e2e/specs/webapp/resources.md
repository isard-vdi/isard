# Resources — Domains › Resources

Human-readable functional specification of the CRUD flows for every
subsection of the **Domains → Resources** screen in the legacy admin
panel. Serves as the contract for the E2E test
`tests/webapp/resources.spec.js`.

## Scope

- **Component**: administration panel.
- **Screen**: **Domains → Resources**
  (`/isard-admin/admin/domains/render/Resources`).
- **Sections covered**:
  - Network QoS (`#table-qos-net`)
  - Disk QoS (`#table-qos-disk`)
  - Interfaces (`#table-interfaces`)
  - Videos (`#videos`)
  - Boots (`#boots`)
  - Remote VPNs (`#table-remotevpn`)
  - Bastion (`#BastionConfig`)
  - Virt Install (`#table-virt-install`)
- **Actions covered per section** (only where the UI provides them):
  - Create, Edit, Change alloweds, Delete, Download config (Remote
    VPN), Open XML editor (Virt Install).
  - For each form submission: the API call must complete with HTTP
    status `< 400` and the row must update in the DataTable.
- **Out of scope**: actual hypervisor-level enforcement of QoS/network
  limits; Bastion DNS external verification; assignment of
  interfaces/videos/boots to specific desktops or templates; Virt
  Install creation (no create button in the UI).

## Common role and prerequisites

| Element | Expected value |
| --- | --- |
| Role | Administrator of the `default` category |
| Session | Logged in to the webapp |
| Seed data | Boots table has at least one entry; Virt Install table has at least one entry |
| Bastion state | Covered in two sub-cases: **disabled** and **enabled** in `isardvdi.cfg` |

## Common data and naming convention

| Field | Sample value | Notes |
| --- | --- | --- |
| Name (most resources) | `e2e-<resource>-<worker>-<timestamp>` | 4–50 chars; pattern `^[\-_àèìòùáéíóúñçÀÈÌÒÙÁÉÍÓÚÑÇ .a-zA-Z0-9:/]+$` |
| Description | `e2e <resource> created at <ISO timestamp>` | 0–255 chars; free text |

Each test that creates a resource stores its generated name (or id) in
`testInfo.annotations` so that `afterEach` can look it up by name and
delete it even if assertions fail mid-scenario.

---

## Section A — Network QoS

> **Why first?** Network QoS entries are the source of the **QoS
> dropdown** in the Interface creation/edit modal. Scenarios in
> Section C depend on a Net QoS being present.
>
> **Note**: the UI has no **delete** button for Net QoS (it is
> commented out in the source). Cleanup is therefore done via API in
> `afterEach`.

### Scenario A1 — *admin creates a Net QoS and sees it in the table*

#### Given

1. The administrator is on the Resources page and the `#table-qos-net`
   DataTable has loaded.

#### When

1. They press **Add new Net QoS**.
2. The `#modalQosNet` dialog opens.
3. They fill in:
   - **Name**: `e2e-qosnet-<worker>-<timestamp>`
   - **Description**: free text
   - **Inbound** — Average: `10000`, Peak: `15000`, Floor: `5000`,
     Burst: `20000` (KBytes/s)
   - **Outbound** — Average: `10000`, Peak: `15000`, Burst: `20000`
     (KBytes/s)
4. They press **Add Net QoS**.

#### Then

1. `POST /api/v4/admin/table/add/qos_net` is called with a JSON body
   that contains a `bandwidth.inbound` and `bandwidth.outbound`
   object (values are mapped from the form's `qos-bandwidth-*`
   fields); the response status is `< 400`.
2. The dialog closes.
3. A success PNotify notification appears ("Network Qos created
   successfully").
4. A new row with the entered name and description appears in
   `#table-qos-net` (via WebSocket or DataTable reload).

---

### Scenario A2 — *admin edits a Net QoS's bandwidth values*

#### Given

1. A Net QoS created by this test exists and is visible in
   `#table-qos-net`.

#### When

1. On the Net QoS row, they press the **edit** icon (pencil).
2. `POST /api/v4/admin/table/qos_net` is called with `{"id":
   "<id>"}` to fetch the current values; the form is pre-filled with
   them (name field is disabled).
3. They change the **Inbound Average** to `8000` and the
   **Description** to new text.
4. They press **Add Net QoS** (the button label is the same for
   edit).

#### Then

1. `PUT /api/v4/admin/table/update/qos_net` is called with the
   updated bandwidth structure; the response status is `< 400`.
2. The dialog closes.
3. A success PNotify notification appears ("Network Qos updated
   successfully").
4. The row in `#table-qos-net` reflects the new description.

---

## Section B — Disk QoS

> Disk QoS has full CRUD: create, edit, alloweds, and delete.

### Scenario B1 — *admin creates a Disk QoS and sees it in the table*

#### Given

1. The administrator is on the Resources page and `#table-qos-disk`
   has loaded.

#### When

1. They press **Add new Disk QoS**.
2. `#modalQosDisk` opens with the title "Add new Disk QoS" and the
   footer button labelled "Add Disk QoS".
3. They fill in:
   - **Name**: `e2e-qosdisk-<worker>-<timestamp>`
   - **Description**: free text
   - **Throughputs** — Read limit: `50`, Write limit: `50` (MB/s);
     Read burst: `80`, Write burst: `80` (MB/s); Read burst
     duration: `2`, Write burst duration: `2` (seconds)
   - **IOPS** — Read limit: `10000`, Write limit: `10000`; Read
     burst: `15000`, Write burst: `15000`; Read duration: `2`, Write
     duration: `2` (seconds); IOPS size: `4` (KB)
4. They press **Add Disk QoS**.

#### Then

1. `POST /api/v4/qos_disk` is called with an `iotune` object whose
   byte-level keys are derived by multiplying the MB/s values by
   `1024 * 1024`; the response status is `< 400`.
2. The dialog closes.
3. A success PNotify notification appears ("Disk QoS created
   successfully").
4. A new row with the entered name appears in `#table-qos-disk`.

---

### Scenario B2 — *admin edits a Disk QoS*

#### Given

1. A Disk QoS created by this test exists.

#### When

1. On the Disk QoS row, they press the **edit** icon (pencil).
2. The dialog opens with the title "Edit Disk QoS" and the footer
   button labelled "Edit Disk QoS"; fields are pre-filled from
   `POST /api/v4/admin/table/qos_disk` with `{"id": "<id>"}`.
3. They change the **Description** and the **Read limit (MB/s)** to a
   new value (e.g. `40`).
4. They press **Edit Disk QoS**.

#### Then

1. `PUT /api/v4/qos_disk` is called with the updated `iotune` object;
   the response status is `< 400`.
2. The dialog closes.
3. A success PNotify notification appears ("Disk QoS updated
   successfully").
4. The row in `#table-qos-disk` reflects the new description.

---

### Scenario B3 — *admin changes alloweds for a Disk QoS*

#### Given

1. A Disk QoS created by this test exists.

#### When

1. On the row, they press the **alloweds** icon (people).
2. The shared modal `#modalAlloweds` opens with the title "Apply to
   roles" and subtitle "This QoS will be applied to users roles
   desktops when starting".
3. They make any change to the allowed roles/categories/groups/users
   and confirm.

#### Then

1. The alloweds API call completes with status `< 400`.
2. The modal closes.

---

### Scenario B4 — *admin deletes a Disk QoS*

#### Given

1. A Disk QoS created by this test exists.

#### When

1. On the row, they press the **delete** icon (red ×).
2. A PNotify confirmation dialog appears: "Are you sure you want to
   delete disk QoS: `<name>`?".
3. They confirm.

#### Then

1. `DELETE /api/v4/admin/table/qos_disk/<id>` is called; response
   status is `< 400`.
2. The row disappears from `#table-qos-disk` (via WebSocket delete
   event or DataTable redraw).
3. A "Deleted" success PNotify notification appears.

---

## Section C — Interfaces

> **Prerequisite**: a Net QoS entry exists (created in Scenario A1 or
> by the seed). The interface creation modal populates its **QoS**
> dropdown from `POST /api/v4/admin/table/qos_net`.
>
> **Interface delete warning**: deleting an interface **stops all
> running desktops** that use it before removing the interface from
> their definitions. This side-effect is stated in the confirmation
> dialog; the E2E test creates interfaces with no desktops attached so
> the stop-desktops path is not exercised.

### Common data for Interfaces

| Field | Value |
| --- | --- |
| Name | `e2e-iface-<type>-<worker>-<timestamp>` |
| Description | `e2e interface <type> created at <ISO timestamp>` |
| Model | `virtio` |
| QoS | Net QoS created in A1 (or `unlimited` if that entry is absent) |

### Scenario C1 — *admin creates a Bridge interface*

#### Given

1. The administrator is on the Resources page, `#table-interfaces` has
   loaded, and at least one Net QoS exists.

#### When

1. They press **Add new interface**.
2. `#modalInterfaces` opens; the QoS dropdown is populated via
   `populateDropdown('qos_net', '#qos_id', 'unlimited', false)`.
3. They fill in name and description.
4. In **Type**, they select **Bridge**.
5. The `#ifname_label` updates to "Input interface name" and
   `#ifname` becomes a free-text field.
6. They enter an interface name (e.g. `br0`).
7. They select Model: **virtio** and QoS: the Net QoS from A1.
8. They press **Add interface**.

#### Then

1. `POST /api/v4/admin/table/add/interfaces` is called with body
   `{name, description, kind: "bridge", net: <ifname value>, model,
   qos_id, allowed: {…}}` (the `net` field is set from `ifname`);
   response status `< 400`.
2. The dialog closes and a success PNotify appears ("Interface created
   successfully").
3. The new row appears in `#table-interfaces`.

---

### Scenario C2 — *admin creates a Network interface*

Same flow as C1 but selecting **Network** in the Type dropdown. The
`#ifname_label` updates to "Input network name" and `#ifname` accepts
free text. `kind` in the POST body is `"network"`.

---

### Scenario C3 — *admin creates an OpenVSwitch (OVS) interface*

#### When (differences from C1)

1. In **Type**, they select **OpenVSwitch**.
2. `#ifname_label` updates to "Input vlan ID number"; `#ifname`
   becomes a `type="number"` field with `min=1`, `max=4094`.
3. They enter a valid VLAN ID (e.g. `100`).

#### Then

1. The same POST is made with `kind: "ovs"` and `net: "100"`.
2. Parsley validates that the value is a number between 1 and 4094
   *before* submission.

---

### Scenario C4 — *admin creates a Personal (VLAN range) interface*

#### When (differences from C1)

1. In **Type**, they select **Personal**.
2. `#ifname_label` updates to "Input vlan range (i.e. 2000-3000)";
   `#ifname` accepts text and has the custom `data-parsley-vlanrange`
   validator attached.
3. They enter a valid range, e.g. `2000-3000`.

#### Then

1. The POST is made with `kind: "personal"` and `net: "2000-3000"`.
2. Parsley's `vlanrange` validator ensures: exactly two parts
   separated by `-`, start ≤ end, both in range 1–4094.

#### Error case — invalid vlan range

1. They enter `3000-2000` (start > end) and press **Add interface**.
2. Parsley blocks submission; a validation error appears on `#ifname`.
3. No `POST` is made.

---

### Scenario C5 — *admin edits an interface*

#### Given

1. An interface created by this test exists and is visible in
   `#table-interfaces`.

#### When

1. On the row, they press the **edit** icon (pencil).
2. `POST /api/v4/admin/table/interfaces` with `{"id": "<id>"}` is
   called; the form is pre-filled (name is disabled for the
   `wireguard` system interface, and the `kind` selector and `ifname`
   are locked for it too — but the test uses a non-wireguard
   interface so none of those protections apply).
3. The QoS dropdown is re-populated with the current `qos_id`
   selected.
4. They change the **Description** to new text.
5. They press **Add interface** (same button label).

#### Then

1. `PUT /api/v4/admin/table/update/interfaces` is called with the
   updated fields; response status `< 400`.
2. The dialog closes and a success PNotify appears ("Interface updated
   successfully").
3. The row in `#table-interfaces` reflects the new description.

---

### Scenario C6 — *admin changes alloweds for an interface*

#### When

1. On the row, they press the **alloweds** icon (people).
2. The shared `#modalAlloweds` dialog opens.
3. They adjust alloweds and confirm.

#### Then

1. The alloweds call completes with status `< 400` and the modal
   closes.

---

### Scenario C7 — *admin deletes an interface*

#### Given

1. An interface created by this test exists, with no desktops using it.

#### When

1. On the row, they press the **delete** icon (red ×).
2. A PNotify confirmation dialog appears, including the text "WARNING:
   ALL STARTED DESKTOPS WITH THIS INTERFACE WILL BE STOPPED".
3. They confirm.

#### Then

1. `DELETE /api/v4/admin/table/interfaces/<id>` is called; response
   status `< 400`.
2. The row disappears from `#table-interfaces`.
3. A "Deleted" success PNotify notification appears.

---

## Section D — Videos

> The Videos UI only provides **create** and **alloweds** actions.
> The edit and delete buttons are commented out in the source. No
> scenario tests edit or delete.

### Scenario D1 — *admin creates a Video and sees it in the table*

#### When

1. They press **Add new video**.
2. `#modalVideos` opens.
3. They fill in:
   - **Name**: `e2e-video-<worker>-<timestamp>`
   - **Description**: free text
   - **Model**: `qxl` (any value from the dropdown: vga, cirrus,
     vmvga, xen, vbox, qxl, virtio)
   - **Heads**: `1` (slider, range 1–4 via ionRangeSlider)
   - **RAM**: `8000` KB (slider, range 8000–128000 KB)
   - **vRAM**: `8000` KB (slider, range 8000–128000 KB)
   - **Alloweds**: defaults (no changes)
4. They press **Add video**.

#### Then

1. `POST /api/v4/admin/table/add/videos` is called; response status
   `< 400`.
2. The dialog closes and a success PNotify appears ("Video created
   successfully").
3. A new row appears in `#videos`.

---

### Scenario D2 — *admin changes alloweds for a Video*

#### When

1. On the video row, they press the **alloweds** icon.
2. The `#modalAlloweds` dialog opens.
3. They adjust alloweds and confirm.

#### Then

1. The alloweds call completes with status `< 400` and the modal
   closes.

---

## Section E — Boots

> The Boots table is **read-only** from a data-management perspective:
> there is no create or delete button in the UI. The only action
> available is managing **alloweds**.

### Scenario E1 — *admin changes alloweds for a Boot entry*

#### Given

1. The `#boots` DataTable has loaded and at least one boot entry
   exists (provided by seed data).

#### When

1. On a boot row, they press the **alloweds** icon (people).
2. The `#modalAlloweds` dialog opens.
3. They adjust alloweds and confirm.

#### Then

1. The alloweds call completes with status `< 400` and the modal
   closes.
2. No row is added or removed from `#boots`.

---

## Section F — Remote VPNs

> Remote VPN create and update both POST to the same endpoint
> (`/api/v4/admin/table/add/remotevpn`). The backend distinguishes
> upsert semantics by whether the record with the given name already
> exists. In both paths the `id` field is removed from the payload
> before sending.

### Scenario F1 — *admin creates a Remote VPN and sees it in the table*

#### When

1. They press **Add new VPN client**.
2. `#modalRemotevpn` opens.
3. They fill in:
   - **Name**: `e2e-vpn-<worker>-<timestamp>`
   - **Description**: free text
   - **Optional extra Routed Hosts/Networks**: left blank (optional
     field; pattern `^[/.,0-9]+$` if filled)
4. They press **Add VPN client**.

#### Then

1. `POST /api/v4/admin/table/add/remotevpn` is called with
   `{name, description, allowed: {roles: false, …}}`; response status
   `< 400`.
2. The dialog closes and a success PNotify appears ("Remote VPN
   created successfully").
3. A new row appears in `#table-remotevpn` (columns: name,
   description, WireGuard address, extra nets, connected indicator).

---

### Scenario F2 — *admin edits a Remote VPN*

> **Current UI reality:** the row action column does **not** render an
> edit button for Remote VPNs right now. The handler still exists in
> `domains_resources.js`, but the button HTML is commented out, so this
> scenario cannot be exercised from the current webapp.

#### Given

1. A Remote VPN created by this test exists.

#### When

1. They inspect the row action column.

#### Then

1. No **edit** icon is available in the rendered UI.
2. The scenario is documented as currently **not automatable through
   webapp** until the button is exposed again.

---

### Scenario F3 — *admin changes alloweds for a Remote VPN*

#### When

1. On the row, they press the **alloweds** icon (people).
2. The `#modalAlloweds` dialog opens.
3. They adjust alloweds and confirm.

#### Then

1. The alloweds call completes with status `< 400` and the modal
   closes.

---

### Scenario F4 — *admin deletes a Remote VPN*

#### When

1. On the row, they press the **delete** icon (red ×).
2. A PNotify confirmation dialog appears: "Are you sure you want to
   delete client VPN: `<name>`?".
3. They confirm.

#### Then

1. `DELETE /api/v4/admin/table/remotevpn/<id>` is called; response
   status `< 400`.
2. The row disappears from `#table-remotevpn`.
3. A "Deleted" success PNotify notification appears.

---

### Scenario F5 — *admin downloads VPN config for the current OS*

#### Given

1. A Remote VPN exists in the table (can be a seed entry; does not
   need to be created by this test).

#### When

1. On the row, they press the **download** icon (green arrow).

#### Then

1. `GET /api/v4/remote_vpn/<id>/config/<os>` is called (where `<os>`
   is determined by `getOS()` from the browser user-agent); response
   status `< 400`.
2. The browser triggers a file download with name
   `<response.name>.<response.ext>` and MIME type `<response.mime>`.
   The test verifies the download was initiated (e.g. by checking the
   download event or the `<a>` element creation).

---

## Section G — Bastion

> Bastion visibility is controlled by `bastion_enabled_in_cfg` (from
> the isardvdi.cfg `BASTION_ENABLED` variable). When it is `false`,
> all action buttons are hidden and a descriptive text is shown
> instead. The E2E test covers both branches.
>
> **Important**: the alloweds actions for Bastion carry an
> irreversibility warning (removing a user's access also removes all
> their bastion targets). The modal requires the admin to click **Edit**
> inside the warning before the actual alloweds modal opens.

### Scenario G1 — *Bastion block renders correctly when disabled in cfg*

#### When

1. The page loads and `GET /api/v4/bastion` returns
   `{bastion_enabled_in_cfg: false}`.

#### Then

1. `#bastionStatusLabel` shows text "Bastion disabled in cfg.".
2. `#bastionStatusDescription` shows the descriptive text about
   editing the cfg file.
3. Action buttons (`#btn-alloweds`, `#btn-alloweds-cname`,
   `#btn-delete-disallowed`, `#btn-edit-bastion`) are all **hidden**.

---

### Scenario G2 — *Bastion block renders correctly when enabled in cfg*

#### When

1. `GET /api/v4/bastion` returns
   `{bastion_enabled_in_cfg: true, bastion_ssh_port: 2222}`.

#### Then

1. `#bastionStatusLabel` shows "Bastion enabled in cfg. SSH port:
   2222".
2. All four action buttons are **visible**.

---

### Scenario G3 — *admin edits the Bastion configuration*

#### Given

1. Bastion is enabled in cfg (Scenario G2 state).

#### When

1. They press the **edit bastion config** icon (`#btn-edit-bastion`).
2. `#modalEditBastion` opens; `GET /api/v4/bastion` is called again to
   pre-fill the form:
   - `#bastion-enabled` checkbox reflects `bastion_enabled_in_db`.
   - `#bastion-domain` text input is filled with current
     `bastion_domain`.
   - `#domain-verification-required` checkbox reflects
     `domain_verification_required`.
3. They toggle **Enabled**, change **Domain** to a test domain value,
   and toggle **Bastion domain verification required**.
4. They press **Update Bastion**.

#### Then

1. `PUT /api/v4/bastion/config` is called with JSON body
   `{enabled: <bool>, bastion_domain: "<value>",
   domain_verification_required: <bool>}`; response status `< 400`.
2. The dialog closes.
3. A success PNotify appears ("Bastion config updated successfully").

---

### Scenario G4 — *admin opens bastion alloweds (accesses via warning dialog)*

#### Given

1. Bastion is enabled in cfg.

#### When

1. They press `#btn-alloweds`.
2. A PNotify **warning** dialog appears with text "Removing a user's
   access will remove the bastion targets for ALL their desktops.
   This action is irreversible." and two buttons: **Edit** and
   **Cancel**.
3. They press **Edit**.

#### Then

1. The warning dialog closes.
2. The shared `#modalAlloweds` dialog opens with `id=1`,
   `name='Bastion'`.
3. They adjust alloweds and confirm; the call completes with status
   `< 400`.

#### Cancel path

If they press **Cancel** in the warning:
1. The warning closes.
2. `#modalAlloweds` does **not** open.

---

### Scenario G5 — *admin opens bastion CNAME alloweds*

Same flow as G4 but triggered by `#btn-alloweds-cname`. The warning
text is "Removing a user's access to edit a custom domain name for
their desktop will remove ALL their configured domain names. This
action is irreversible." and **Edit** opens `#modalAlloweds` with
`id=1, name='Bastion custom domain name'`.

---

### Scenario G6 — *admin deletes disallowed bastion targets — cancel*

#### Given

1. Bastion is enabled in cfg.

#### When

1. They press `#btn-delete-disallowed`.
2. A PNotify error-type confirmation appears explaining that this
   action checks all targets and deletes disallowed ones, is
   **irreversible**, and may take a while.
3. They press **Cancel**.

#### Then

1. The dialog closes.
2. No call to `DELETE /api/v4/bastion/disallowed` is made.

---

### Scenario G7 — *admin deletes disallowed bastion targets — confirm*

#### When

1. Same setup as G6, but they press **Delete**.

#### Then

1. `DELETE /api/v4/bastion/disallowed` is called; response status
   `< 400`.
2. A success PNotify appears ("Disallowed bastion targets are being
   deleted").

---

## Section H — Virt Install

> Virt Install entries are **not created through the UI** (no add
> button exists). The table lists OS definitions used by the engine.
> Available actions per row: **Edit XML** and **Delete**.
>
> **XML editing**: `openXmlSections(data.id, 'virt_install')` opens a
> shared XML editor panel. The E2E test only verifies that the panel
> opens and contains an XML representation of the entry; it does not
> submit XML changes.

### Scenario H1 — *Virt Install table lists entries from the seed*

#### When

1. The page loads and `POST /api/v4/admin/table/virt_install` with
   `{order_by: "name", without: ["xml"]}` is called.

#### Then

1. Response status is `< 400` and the body is a non-empty array.
2. `#table-virt-install` renders at least one row with columns: id,
   name, icon, vers, and the action buttons (XML, delete).

---

### Scenario H2 — *admin opens the XML editor for a Virt Install entry*

#### Given

1. A row exists in `#table-virt-install`.

#### When

1. On the row, they press the **XML** icon (file-code-o).

#### Then

1. `openXmlSections(data.id, 'virt_install')` is called (bare
   minimum: the XML editor panel/modal becomes visible and contains
   non-empty content).
2. No assertion on saving XML — out of scope for this spec.

---

### Scenario H3 — *admin deletes a Virt Install entry*

> **Caution**: this scenario requires a virt_install seed entry that
> is safe to delete (not referenced by any domain or template in the
> test database). Mark as `test.skip` if no such safe entry is
> identifiable.

#### When

1. On the row, they press the **delete** icon (red ×).
2. A PNotify confirmation dialog appears: "Are you sure you want to
   delete virt_install: `<name>`?".
3. They confirm.

#### Then

1. `DELETE /api/v4/admin/table/virt_install/<id>` is called; response
   status `< 400`.
2. The row disappears from `#table-virt-install` (DataTable reloads
   after delete via `virtinstall_table.ajax.reload()`).

---

## Cleanup (afterEach)

1. Any resource created during the test is looked up by name/id and
   deleted via API (using `DELETE` on the respective endpoint or
   `admin/table` endpoint as appropriate).
2. The Net QoS created in A1 is deleted via API after all Interface
   scenarios that depend on it have run (`DELETE` on the generic table
   endpoint since there is no dedicated apiv4 delete for `qos_net`).
3. Cleanup errors are silenced to avoid masking primary failure
   reasons.

---

## Expected results — global summary

| Scenario | Covered? | Key checks |
| --- | --- | --- |
| A1 — Net QoS create | ✅ | `POST admin/table/add/qos_net` 2XX; row in table |
| A2 — Net QoS edit | ✅ | `PUT admin/table/update/qos_net` 2XX; row updated |
| B1 — Disk QoS create | ✅ | `POST /api/v4/qos_disk` 2XX; row in table |
| B2 — Disk QoS edit | ✅ | `PUT /api/v4/qos_disk` 2XX; row updated |
| B3 — Disk QoS alloweds | ✅ | Modal opens, alloweds call 2XX |
| B4 — Disk QoS delete | ✅ | Confirmation dialog, `DELETE admin/table/qos_disk/{id}` 2XX; row removed |
| C1 — Interface Bridge | ✅ | `kind=bridge`, `POST admin/table/add/interfaces` 2XX |
| C2 — Interface Network | ✅ | `kind=network`, same POST 2XX |
| C3 — Interface OVS | ✅ | `kind=ovs`, ifname numeric 1–4094, same POST 2XX |
| C4 — Interface Personal | ✅ | `kind=personal`, vlanrange validated, same POST 2XX |
| C4 error — invalid range | ✅ | Parsley blocks submit; no POST |
| C5 — Interface edit | ✅ | `PUT admin/table/update/interfaces` 2XX; row updated |
| C6 — Interface alloweds | ✅ | Modal opens, call 2XX |
| C7 — Interface delete | ✅ | Confirmation with desktop-stop warning; `DELETE admin/table/interfaces/{id}` 2XX |
| D1 — Video create | ✅ | `POST admin/table/add/videos` 2XX; row in table |
| D2 — Video alloweds | ✅ | Modal opens, call 2XX |
| E1 — Boot alloweds | ✅ | Modal opens, call 2XX |
| F1 — Remote VPN create | ✅ | `POST admin/table/add/remotevpn` 2XX; row in table |
| F2 — Remote VPN edit | ⚠️ | Handler exists, but no edit button is rendered in current UI |
| F3 — Remote VPN alloweds | ✅ | Modal opens, call 2XX |
| F4 — Remote VPN delete | ✅ | Confirmation; `DELETE admin/table/remotevpn/{id}` 2XX; row removed |
| F5 — VPN config download | ✅ | `GET /api/v4/remote_vpn/{id}/config/{os}` 2XX; download triggered |
| G1 — Bastion disabled in cfg | ✅ | Buttons hidden, status text shown |
| G2 — Bastion enabled in cfg | ✅ | Buttons visible, SSH port shown |
| G3 — Bastion config edit | ✅ | `PUT /api/v4/bastion/config` 2XX; modal closes |
| G4 — Bastion alloweds (warning) | ✅ | Warning → Edit path opens modal; Cancel does not |
| G5 — Bastion CNAME alloweds | ✅ | Same warning pattern, different alloweds target |
| G6 — Delete disallowed targets (cancel) | ✅ | No DELETE call made |
| G7 — Delete disallowed targets (confirm) | ✅ | `DELETE /api/v4/bastion/disallowed` 2XX |
| H1 — Virt Install list | ✅ | Table renders with seed entries |
| H2 — Virt Install XML editor | ✅ | Editor panel opens with non-empty content |
| H3 — Virt Install delete | ⚠️ `conditional skip` | Requires a seed entry safe to delete; `DELETE admin/table/virt_install/{id}` 2XX |

---

## APIs touched by the flows (reference)

| Method | Path | Action |
| --- | --- | --- |
| `POST` | `/api/v4/admin/table/add/qos_net` | Create Net QoS |
| `PUT` | `/api/v4/admin/table/update/qos_net` | Update Net QoS |
| `POST` | `/api/v4/qos_disk` | Create Disk QoS |
| `PUT` | `/api/v4/qos_disk` | Update Disk QoS |
| `DELETE` | `/api/v4/admin/table/qos_disk/{id}` | Delete Disk QoS |
| `POST` | `/api/v4/admin/table/add/interfaces` | Create Interface |
| `PUT` | `/api/v4/admin/table/update/interfaces` | Update Interface |
| `DELETE` | `/api/v4/admin/table/interfaces/{id}` | Delete Interface |
| `POST` | `/api/v4/admin/table/add/videos` | Create Video |
| `POST` | `/api/v4/admin/table/add/remotevpn` | Create **or** update Remote VPN (upsert) |
| `DELETE` | `/api/v4/admin/table/remotevpn/{id}` | Delete Remote VPN |
| `GET` | `/api/v4/remote_vpn/{id}/config/{os}` | Download VPN config |
| `GET` | `/api/v4/bastion` | Get Bastion status / pre-fill edit form |
| `PUT` | `/api/v4/bastion/config` | Update Bastion config |
| `DELETE` | `/api/v4/bastion/disallowed` | Delete disallowed Bastion targets |
| `DELETE` | `/api/v4/admin/table/virt_install/{id}` | Delete Virt Install entry |
| `POST` | `/api/v4/admin/table/{table}` | Generic lookup for pre-filling edit forms and the alloweds modal |
| `POST` | `/api/v4/admin/table/qos_net` (pluck) | Populate QoS dropdown in Interface modal |

### Notes on non-standard patterns

- **Remote VPN upsert**: both create and update call
  `POST /api/v4/admin/table/add/remotevpn` without an `id` in the
  body. The backend differentiates by whether the record already
  exists.
- **Disk QoS endpoints** use `/api/v4/qos_disk` (a dedicated route),
  while most other resources use the generic
  `/api/v4/admin/table/add/<table>` / `update/<table>` convention.
- **Disk QoS unit conversion**: form fields use human-friendly units
  (MB/s, KB/s, IOPS, seconds) that the frontend converts to bytes
  before sending (`QosDiskParse`).
- **Net QoS unit conversion**: form fields use KBytes/s; the frontend
  prefixes keys with `@` in `bandwidth.inbound` /
  `bandwidth.outbound` objects (`QosNetParse`).
- **Interface `net` field**: the `net` field sent in the API payload
  is derived from the `ifname` form input, not from a field named
  `net`.

## Cases not covered (future)

- **Net QoS delete**: no delete button exists in the UI; can only be
  cleaned up via direct API call. If the UI adds a delete button, add
  a Scenario A3.
- **Video edit and delete**: buttons are commented out in the source
  code; add Scenarios D3/D4 if they are re-enabled.
- **Virt Install create**: no add button in the UI; would require a
  file upload mechanism.
- **Interface with running desktops**: delete flow that actually stops
  running desktops before removing the interface.
- **Wireguard interface**: the system interface `wireguard` has its
  type selector and ifname locked; editing it is protected at the UI
  level and is not exercised by these tests.
- **Remote VPN with extra nets**: the optional "extra Routed
  Hosts/Networks" field (pattern `^[/.,0-9]+$`) is not covered by
  a dedicated scenario; add one if that path needs explicit
  verification.
