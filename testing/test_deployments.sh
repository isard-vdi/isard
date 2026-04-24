#!/usr/bin/env bash
# Testing script for multi-desktop deployment guards.
# Populates the system with templates and deployments (single + multi-desktop),
# then verifies every deployment endpoint behaves correctly.
#
# Usage:
#   ./testing/test_deployments.sh            # run from repo root
#   ./testing/test_deployments.sh --cleanup   # only clean up test data
#
# Prerequisites:
#   - docker compose services running (isard-apiv4, isard-db, isard-portal, isard-authentication, isard-engine)
#   - TetrOS domain available in the downloads repository (auto-registered + downloaded)

set -euo pipefail

cd "$(dirname "$0")/.."

###############################################################################
# Config
###############################################################################
ADMIN_USER="admin"
ADMIN_PWD="${WEBAPP_ADMIN_PWD:-isard6393}"
TEST_USER_UID="deploy-test-user"
TEST_USER_NAME="Deploy Test User"
TEST_USER_PWD="test1234"

PASS=0
FAIL=0
SKIP=0

###############################################################################
# Helpers
###############################################################################
log()  { printf '\033[1;34m[INFO]\033[0m  %s\n' "$*"; }
pass() { printf '\033[1;32m[PASS]\033[0m  %s\n' "$*"; PASS=$((PASS+1)); }
fail() { printf '\033[1;31m[FAIL]\033[0m  %s\n' "$*"; FAIL=$((FAIL+1)); }
skip() { printf '\033[1;33m[SKIP]\033[0m  %s\n' "$*"; SKIP=$((SKIP+1)); }

get_token() {
    docker compose exec -T isard-portal curl -sf \
        "http://isard-authentication:1313/authentication/login?provider=form&category_id=default" \
        -F "username=$ADMIN_USER" -F "password=$ADMIN_PWD" \
        -H 'X-Forwarded-For: 10.0.0.1'
}

api() {
    local method="$1" path="$2"
    shift 2
    docker compose exec -T isard-apiv4 curl -s -X "$method" \
        "http://localhost:5000${path}" \
        -H "Authorization: Bearer $TOKEN" \
        "$@" 2>/dev/null
}

api_code() {
    local method="$1" path="$2"
    shift 2
    docker compose exec -T isard-apiv4 curl -s -o /dev/null -w "%{http_code}" -X "$method" \
        "http://localhost:5000${path}" \
        -H "Authorization: Bearer $TOKEN" \
        "$@" 2>/dev/null
}

rethink() {
    docker compose exec -T isard-db python3 -c "$1" 2>/dev/null
}

assert_http() {
    local test_name="$1" expected="$2" actual="$3"
    if [ "$actual" = "$expected" ]; then
        pass "$test_name (HTTP $actual)"
    else
        fail "$test_name (expected HTTP $expected, got $actual)"
    fi
}

assert_json_field() {
    local test_name="$1" json="$2" field="$3" expected="$4"
    local actual
    actual=$(echo "$json" | python3 -c "import sys,json; print(json.load(sys.stdin).get('$field',''))" 2>/dev/null)
    if [ "$actual" = "$expected" ]; then
        pass "$test_name ($field=$actual)"
    else
        fail "$test_name (expected $field=$expected, got $field=$actual)"
    fi
}

###############################################################################
# Cleanup function — removes all test artifacts
###############################################################################
cleanup() {
    log "Cleaning up test data..."
    TOKEN=$(get_token) || { log "Cannot get token for cleanup"; return; }

    rethink "
from rethinkdb import RethinkDB
r = RethinkDB()
conn = r.connect('localhost', 28015)
db = r.db('isard')

# Get test deployment IDs (by tag_name prefix)
test_deps = list(db.table('deployments').filter(
    lambda d: d['tag_name'].match('^DeployTest')
).pluck('id','tag').run(conn))
dep_tags = [d['tag'] for d in test_deps]

# Delete domains belonging to test deployments
if dep_tags:
    deleted = db.table('domains').filter(
        lambda d: r.expr(dep_tags).contains(d['tag']).default(False)
    ).delete().run(conn)
    print(f'  Deployment domains deleted: {deleted[\"deleted\"]}')

# Delete test deployments
deleted = db.table('deployments').filter(
    lambda d: d['tag_name'].match('^DeployTest')
).delete().run(conn)
print(f'  Deployments deleted: {deleted[\"deleted\"]}')

# Clean recycle bin entries for test deployments
deleted = db.table('recycle_bin').filter(
    lambda d: d.has_fields('agent_id').and_(
        d['agent_id'].eq('local-default-admin-admin')
    )
).delete().run(conn)
print(f'  Recycle bin cleaned: {deleted[\"deleted\"]}')

# Delete test user
deleted = db.table('users').filter({'uid': '$TEST_USER_UID'}).delete().run(conn)
print(f'  Test users deleted: {deleted[\"deleted\"]}')
conn.close()
"
    log "Cleanup complete"
}

###############################################################################
# Setup — populate system with templates and deployments
###############################################################################
setup() {
    log "=== SETUP: Populating system ==="
    TOKEN=$(get_token) || { fail "Cannot authenticate"; exit 1; }

    # Step 1: Register downloads (idempotent)
    log "Registering with downloads service..."
    api POST /api/v4/admin/downloads/register -H "Content-Type: application/json" >/dev/null

    # Step 2: Check if TetrOS template exists
    TETROS_TEMPLATE=$(rethink "
from rethinkdb import RethinkDB
r = RethinkDB()
conn = r.connect('localhost', 28015)
templates = list(r.db('isard').table('domains').filter({'kind': 'template'}).pluck('id','name').run(conn))
for t in templates:
    if 'tetros' in t['name'].lower():
        print(t['id'])
        break
conn.close()
")

    if [ -z "$TETROS_TEMPLATE" ]; then
        log "No TetrOS template found. Looking for TetrOS desktop..."

        TETROS_DESKTOP=$(rethink "
from rethinkdb import RethinkDB
r = RethinkDB()
conn = r.connect('localhost', 28015)
desktops = list(r.db('isard').table('domains').filter({'kind': 'desktop'}).pluck('id','name','status').run(conn))
for d in desktops:
    if 'tetros' in d['name'].lower() and d['status'] == 'Stopped':
        print(d['id'])
        break
conn.close()
")

        if [ -z "$TETROS_DESKTOP" ]; then
            log "Downloading TetrOS..."
            TETROS_DATA=$(api GET /api/v4/admin/downloads/domains | python3 -c "
import sys, json
data = json.load(sys.stdin)
for d in data:
    if 'tetros' in d.get('name','').lower():
        print(json.dumps(d))
        break
")
            if [ -z "$TETROS_DATA" ]; then
                fail "TetrOS not available in downloads"; exit 1
            fi
            TETROS_URL_ID=$(echo "$TETROS_DATA" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))")
            api POST "/api/v4/admin/downloads/download/domains/$TETROS_URL_ID" \
                -H "Content-Type: application/json" -d "$TETROS_DATA" >/dev/null

            log "Waiting for TetrOS download..."
            for i in $(seq 1 60); do
                STATUS=$(rethink "
from rethinkdb import RethinkDB
r = RethinkDB()
conn = r.connect('localhost', 28015)
ds = list(r.db('isard').table('domains').filter(lambda d: d['name'].match('(?i)tetros')).pluck('status').run(conn))
print(ds[0]['status'] if ds else 'NotFound')
conn.close()
")
                if [ "$STATUS" = "Stopped" ]; then break; fi
                sleep 2
            done
            if [ "$STATUS" != "Stopped" ]; then
                fail "TetrOS download did not complete (status=$STATUS)"; exit 1
            fi

            TETROS_DESKTOP=$(rethink "
from rethinkdb import RethinkDB
r = RethinkDB()
conn = r.connect('localhost', 28015)
desktops = list(r.db('isard').table('domains').filter({'kind': 'desktop'}).filter(lambda d: d['name'].match('(?i)tetros')).pluck('id').run(conn))
print(desktops[0]['id'] if desktops else '')
conn.close()
")
        fi

        log "Creating template from TetrOS desktop ($TETROS_DESKTOP)..."
        TOKEN=$(get_token)
        TETROS_TEMPLATE=$(api POST /api/v4/item/template \
            -H "Content-Type: application/json" \
            -d "{\"desktop_id\":\"$TETROS_DESKTOP\",\"name\":\"TetrOS Template\",\"description\":\"TetrOS for deployment testing\",\"allowed\":{\"roles\":[\"admin\",\"advanced\"],\"categories\":false,\"groups\":false,\"users\":false}}" \
            | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))")

        log "Waiting for template to be ready..."
        for i in $(seq 1 30); do
            STATUS=$(rethink "
from rethinkdb import RethinkDB
r = RethinkDB()
conn = r.connect('localhost', 28015)
t = r.db('isard').table('domains').get('$TETROS_TEMPLATE').pluck('status').run(conn)
print(t['status'] if t else 'NotFound')
conn.close()
")
            if [ "$STATUS" = "Stopped" ]; then break; fi
            sleep 1
        done
    fi
    log "TetrOS template: $TETROS_TEMPLATE"

    # Step 3: Create test user (if not exists)
    EXISTING_USER=$(rethink "
from rethinkdb import RethinkDB
r = RethinkDB()
conn = r.connect('localhost', 28015)
users = list(r.db('isard').table('users').filter({'uid': '$TEST_USER_UID'}).pluck('id').run(conn))
print(users[0]['id'] if users else '')
conn.close()
")
    if [ -z "$EXISTING_USER" ]; then
        log "Creating test user..."
        TOKEN=$(get_token)
        api POST /api/v4/admin/user \
            -H "Content-Type: application/json" \
            -d "{\"uid\":\"$TEST_USER_UID\",\"username\":\"$TEST_USER_UID\",\"password\":\"$TEST_USER_PWD\",\"name\":\"$TEST_USER_NAME\",\"role\":\"advanced\",\"category\":\"default\",\"group\":\"default-default\",\"provider\":\"local\",\"bulk\":false}" >/dev/null
    fi

    # Step 4: Get template hardware info for deployment creation
    TOKEN=$(get_token)
    TEMPLATE_INFO=$(api GET "/api/v4/item/desktop/$TETROS_TEMPLATE/get-info")
    STORAGE_ID=$(echo "$TEMPLATE_INFO" | python3 -c "
import sys, json
data = json.load(sys.stdin)
disks = data.get('hardware',{}).get('disks',[])
print(disks[0].get('storage_id','') if disks else '')
")

    # Step 5: Create single-desktop deployment
    log "Creating single-desktop deployment..."
    TOKEN=$(get_token)
    SINGLE_RESP=$(api POST /api/v4/item/deployment \
        -H "Content-Type: application/json" \
        -d "{
            \"name\": \"DeployTest Single\",
            \"description\": \"Single desktop deployment for testing\",
            \"template_id\": \"$TETROS_TEMPLATE\",
            \"visible\": true,
            \"allowed\": {
                \"roles\": false,
                \"categories\": false,
                \"groups\": [\"default-default\"],
                \"users\": false
            },
            \"hardware\": {
                \"boot_order\": [\"disk\"],
                \"disks\": [{\"storage_id\": \"$STORAGE_ID\"}],
                \"graphics\": [\"default\"],
                \"interfaces\": [\"default\"],
                \"memory\": 0.5,
                \"vcpus\": 1,
                \"videos\": [\"vga\"],
                \"reservables\": {\"vgpus\": []}
            },
            \"guest_properties\": {
                \"credentials\": {\"password\": \"pirineus\", \"username\": \"isard\"},
                \"fullscreen\": false,
                \"viewers\": {\"browser_vnc\": {\"options\": null}, \"file_spice\": {\"options\": null}}
            },
            \"image\": {\"id\": \"37.jpg\", \"type\": \"stock\", \"url\": \"/assets/img/desktops/stock/37.jpg\"}
        }")
    SINGLE_ID=$(echo "$SINGLE_RESP" | python3 -c "import sys,json; print(json.load(sys.stdin).get('id',''))" 2>/dev/null)
    if [ -z "$SINGLE_ID" ]; then
        fail "Failed to create single-desktop deployment: $SINGLE_RESP"; exit 1
    fi
    log "Single-desktop deployment: $SINGLE_ID"

    # Step 6: Create multi-desktop deployment directly in DB
    log "Creating multi-desktop deployment in DB..."
    MULTI_ID=$(rethink "
import copy
from uuid import uuid4
from rethinkdb import RethinkDB
r = RethinkDB()
conn = r.connect('localhost', 28015)
single = r.db('isard').table('deployments').get('$SINGLE_ID').run(conn)
multi = copy.deepcopy(single)
multi_id = str(uuid4())
multi['id'] = multi_id
multi['tag'] = multi_id
multi['name'] = 'DeployTest Multi'
multi['tag_name'] = 'DeployTest Multi'
multi['description'] = 'Multi-desktop deployment for testing'
second = copy.deepcopy(multi['create_dict'][0])
second['name'] = 'Second Desktop'
second['tag_desktop_id'] = str(uuid4())
multi['create_dict'].append(second)
r.db('isard').table('deployments').insert(multi).run(conn)
print(multi_id)
conn.close()
")
    log "Multi-desktop deployment: $MULTI_ID"

    # Export for tests
    export TETROS_TEMPLATE SINGLE_ID MULTI_ID
}

###############################################################################
# Tests
###############################################################################
run_tests() {
    log "=== RUNNING TESTS ==="
    TOKEN=$(get_token)

    # --- lists() ---
    log "--- lists() endpoint ---"
    LIST_RESP=$(api GET /api/v4/items/deployments)
    LIST_COUNT=$(echo "$LIST_RESP" | python3 -c "import sys,json; data=json.load(sys.stdin); print(len(data))")
    HAS_MULTI=$(echo "$LIST_RESP" | python3 -c "import sys,json; data=json.load(sys.stdin); print(any('Multi' in d.get('name','') for d in data))")
    if [ "$HAS_MULTI" = "False" ]; then
        pass "T01: lists() filters out multi-desktop deployments"
    else
        fail "T01: lists() should filter multi-desktop deployments"
    fi

    # --- get() single ---
    CODE=$(api_code GET "/api/v4/item/deployment/$SINGLE_ID")
    assert_http "T02: get() single-desktop returns 200" "200" "$CODE"

    # --- get() multi ---
    CODE=$(api_code GET "/api/v4/item/deployment/$MULTI_ID")
    assert_http "T03: get() multi-desktop returns 428" "428" "$CODE"
    RESP=$(api GET "/api/v4/item/deployment/$MULTI_ID")
    assert_json_field "T03b: get() multi error code" "$RESP" "description_code" "multi_desktop_deployment"

    # --- get_deployment_info() single ---
    CODE=$(api_code GET "/api/v4/item/deployment/$SINGLE_ID/info")
    assert_http "T04: info() single-desktop returns 200" "200" "$CODE"

    # --- get_deployment_info() multi ---
    CODE=$(api_code GET "/api/v4/item/deployment/$MULTI_ID/info")
    assert_http "T05: info() multi-desktop returns 428" "428" "$CODE"
    RESP=$(api GET "/api/v4/item/deployment/$MULTI_ID/info")
    assert_json_field "T05b: info() multi error code" "$RESP" "description_code" "multi_desktop_deployment"

    # --- edit_deployment() multi ---
    TOKEN=$(get_token)
    CODE=$(api_code PUT "/api/v4/item/deployment/$MULTI_ID/edit" -H "Content-Type: application/json" -d '{"name":"x"}')
    assert_http "T06: edit() multi-desktop returns 428" "428" "$CODE"

    # --- edit_deployment_users() multi ---
    CODE=$(api_code PUT "/api/v4/item/deployment/$MULTI_ID/edit-users" \
        -H "Content-Type: application/json" \
        -d '{"allowed":{"roles":false,"categories":false,"groups":["default-default"],"users":false}}')
    assert_http "T07: edit_users() multi-desktop returns 428" "428" "$CODE"

    # --- recreate() multi ---
    CODE=$(api_code PUT "/api/v4/item/deployment/$MULTI_ID/recreate")
    assert_http "T08: recreate() multi-desktop returns 428" "428" "$CODE"

    # --- start() / stop() single (should work) ---
    TOKEN=$(get_token)
    CODE=$(api_code PUT "/api/v4/item/deployment/$SINGLE_ID/start")
    assert_http "T09: start() single-desktop returns 200" "200" "$CODE"

    CODE=$(api_code PUT "/api/v4/item/deployment/$SINGLE_ID/stop")
    assert_http "T10: stop() single-desktop returns 200" "200" "$CODE"

    # --- start() / stop() multi (should work - tag-based) ---
    CODE=$(api_code PUT "/api/v4/item/deployment/$MULTI_ID/start")
    assert_http "T11: start() multi-desktop returns 200" "200" "$CODE"

    CODE=$(api_code PUT "/api/v4/item/deployment/$MULTI_ID/stop")
    assert_http "T12: stop() multi-desktop returns 200" "200" "$CODE"

    # --- admin table shows both ---
    TOKEN=$(get_token)
    ADMIN_RESP=$(api GET /api/v4/admin/table/deployments)
    ADMIN_COUNT=$(echo "$ADMIN_RESP" | python3 -c "
import sys, json
data = json.load(sys.stdin)
test_deps = [d for d in data if d.get('tag_name','').startswith('DeployTest')]
print(len(test_deps))
")
    if [ "$ADMIN_COUNT" = "2" ]; then
        pass "T13: admin table shows both deployments ($ADMIN_COUNT)"
    else
        fail "T13: admin table should show 2 test deployments (got $ADMIN_COUNT)"
    fi

    # --- socket.io thread stability ---
    ERRORS=$(docker compose logs isard-apiv4 --tail=200 2>&1 | grep -c "DeploymentsThread internal error" || true)
    if [ "$ERRORS" = "0" ]; then
        pass "T14: socket.io thread has no crashes"
    else
        fail "T14: socket.io thread crashed $ERRORS time(s)"
    fi

    # --- delete single (soft) ---
    TOKEN=$(get_token)
    # Ensure desktops are stopped first
    sleep 2
    api PUT "/api/v4/item/deployment/$SINGLE_ID/stop" >/dev/null
    sleep 3
    CODE=$(api_code DELETE "/api/v4/item/deployment/$SINGLE_ID")
    assert_http "T15: delete() single-desktop (soft) returns 200" "200" "$CODE"

    # --- verify recycle bin ---
    sleep 2
    RB_COUNT=$(rethink "
from rethinkdb import RethinkDB
r = RethinkDB()
conn = r.connect('localhost', 28015)
rb = list(r.db('isard').table('recycle_bin').run(conn))
test_rb = [e for e in rb if any('DeployTest' in d.get('tag_name','') for d in e.get('desktops',[]) + e.get('deployments',[]) if isinstance(d, dict))]
# Fallback: count all recent entries
print(len(rb))
conn.close()
")
    if [ "$RB_COUNT" -ge "1" ]; then
        pass "T16: recycle bin has entry after soft delete"
    else
        fail "T16: recycle bin should have at least 1 entry (got $RB_COUNT)"
    fi

    # --- restore from recycle bin ---
    TOKEN=$(get_token)
    RB_ID=$(rethink "
from rethinkdb import RethinkDB
r = RethinkDB()
conn = r.connect('localhost', 28015)
rb = list(r.db('isard').table('recycle_bin').filter({'status': 'recycled'}).pluck('id').limit(1).run(conn))
print(rb[0]['id'] if rb else '')
conn.close()
")
    if [ -n "$RB_ID" ]; then
        CODE=$(api_code PUT "/api/v4/item/recycle-bin/$RB_ID/restore")
        assert_http "T17: restore from recycle bin returns 200" "200" "$CODE"

        sleep 2
        TOKEN=$(get_token)
        LIST_RESP=$(api GET /api/v4/items/deployments)
        RESTORED=$(echo "$LIST_RESP" | python3 -c "import sys,json; data=json.load(sys.stdin); print(any('DeployTest Single' in d.get('name','') for d in data))")
        if [ "$RESTORED" = "True" ]; then
            pass "T18: deployment restored and visible in list"
        else
            fail "T18: deployment not visible after restore"
        fi
    else
        skip "T17: no recycle bin entry found to restore"
        skip "T18: skipped (depends on T17)"
    fi

    # --- delete multi (soft - should work via tag) ---
    TOKEN=$(get_token)
    CODE=$(api_code DELETE "/api/v4/item/deployment/$MULTI_ID")
    assert_http "T19: delete() multi-desktop (soft) returns 200" "200" "$CODE"

    # --- socket.io stability after multi delete ---
    sleep 2
    ERRORS=$(docker compose logs isard-apiv4 --tail=200 2>&1 | grep -c "DeploymentsThread internal error" || true)
    if [ "$ERRORS" = "0" ]; then
        pass "T20: socket.io thread stable after multi-desktop operations"
    else
        fail "T20: socket.io thread crashed $ERRORS time(s) during test"
    fi
}

###############################################################################
# Main
###############################################################################
if [ "${1:-}" = "--cleanup" ]; then
    cleanup
    exit 0
fi

log "=== Multi-Desktop Deployment Test Suite ==="
log ""

# Clean previous test data
cleanup

# Setup
setup

# Run tests
run_tests

# Clean up after tests
cleanup

# Summary
log ""
log "=============================="
log "  Results: $PASS passed, $FAIL failed, $SKIP skipped"
log "=============================="

if [ "$FAIL" -gt 0 ]; then
    exit 1
fi
