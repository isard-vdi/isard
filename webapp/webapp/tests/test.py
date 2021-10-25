import requests
from rethinkdb import ReqlTimeoutError, r

r.connect("isard-db", 28015).repl()
from pprint import pprint

template_id = "_local-default-admin-admin_Template_TetrOS"
user_id = "_local-default-admin-admin"
template = (
    r.db("isard")
    .table("domains")
    .get(template_id)
    .pluck("id", "name", "kind", "user")
    .run()
)
derivated = list(
    r.db("isard")
    .table("domains")
    .pluck("id", "name", "kind", "user", "status", "parents")
    .filter(lambda derivates: derivates["parents"].contains(template_id))
    .run()
)
doms = []
for d in derivated:
    d["parent"] = d["parents"][-1]
    tmp = d.pop("parents")
# pprint(derivated)

# tree = [{"title": template_id, "expanded": True, "selected": True}]
# , children: [


def domain_recursive_count(self, id, tree):
    doms = [d for d in domains if d["origin"] == id]
    for dom in doms:
        tree.append()
        count += self.domain_recursive_count(dom["id"], domains)
    return count


def build_tree(elems):
    elem_with_children = {}

    def _build_children_sub_tree(parent):
        cur_dict = {
            "id": parent,
            "name": item["name"]
            # put whatever attributes here
        }
        if parent in elem_with_children.keys():
            cur_dict["children"] = [
                _build_children_sub_tree(cid) for cid in elem_with_children[parent]
            ]
        return cur_dict

    for item in elems:
        cid = item["id"]
        pid = item["parents"][-1]
        elem_with_children.setdefault(pid, []).append(cid)

    res = _build_children_sub_tree(template_id)
    return res


def template_delete_list(template_id):
    template = (
        r.db("isard")
        .table("domains")
        .get(template_id)
        .pluck("id", "name", "kind", "user", "status", "parents")
        .run()
    )
    derivated = list(
        r.db("isard")
        .table("domains")
        .pluck("id", "name", "kind", "user", "status", "parents")
        .filter(lambda derivates: derivates["parents"].contains(template_id))
        .run()
    )
    fancyd = []
    for d in derivated:
        fancyd.append(
            {
                "title": d["id"],
                "expanded": True,
                "unselectable": False if template["user"] == d["user"] else True,
                "parent": d["parents"][-1],
            }
        )
    return fancyd


def template_tree(template_id):
    levels = {}
    derivated = template_delete_list(template_id)
    for n in derivated:
        levels.setdefault(n["parent"], []).append(n)
    return template_rtree(template_id, levels)


def template_rtree(template_id, levels):
    nodes = [dict(n) for n in levels.get(template_id, [])]
    for n in nodes:
        children = template_rtree(n["title"], levels)
        if children:
            n["children"] = children
    return nodes


pprint(template_tree(template_id))
# pprint(treeify(derivated))
# pprint(derivated)
# pprint(build_tree(derivated))

# pprint(build_hierarchy(template_id,derivated))
# pprint(derivated)
# build_tree(derivated)
# pprint(build_tree(derivated))
