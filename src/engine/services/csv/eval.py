import csv, os

DATA_EXAMPLE = {
    "load": {
        "hyps": {
            "hdani1": {
                "cpu_percent_free": 0.25,
                "domains_count": 3,
                "ram_percent_free": 63.38
            },
            "hdani2": {
                "cpu_percent_free": 0.16,
                "domains_count": 3,
                "ram_percent_free": 63.59
            },
            "hdani3": {
                "cpu_percent_free": 55.24,
                "domains_count": 4,
                "ram_percent_free": 94.92
            },
            "hdani4": {
                "cpu_percent_free": 78.25,
                "domains_count": 4,
                "ram_percent_free": 94.5
            }
        },
        "started_domains": 14,
        "total_started_domains": 14
    }
}


def eval_to_csv(code, data):
    filename = "{}.csv".format(code)
    filepath = "/isard/csv/{}".format(filename)
    write_header = not os.path.isfile(filepath) # write header if file not exists
    with open(filepath, 'a') as csvfile:
        results = csv.writer(csvfile, delimiter=',')
        if "load" in data:
            if write_header:
                header = ["code"]
                for hyp in sorted(data["load"]["hyps"]):
                    values = data["load"]["hyps"][hyp]
                    for name in sorted(values):
                        header.append("{}_{}".format(hyp, name))
                header.extend(["started_domains", "total_started_domains"])
                results.writerow(header)
            row = [code]
            for hyp in sorted(data["load"]["hyps"]):
                values = data["load"]["hyps"][hyp]
                for name in sorted(values):
                    row.append(values[name])
            row.append(data["load"]["started_domains"])
            row.append(data["load"]["total_started_domains"])
        elif "ux" in data:
            steps = 3
            template = "_admin_ubuntu_17_eval_wget"
            hyps = [hyp for hyp in data["ux"]["step_0"][template]]
            values = [value for value in data["ux"]["step_0"][template][hyps[0]]]
            total_values = [value for value in data["ux"]["total"]]
            if write_header:
                header = ["code"]
                for s in range(steps):
                    str_step = "step_{}".format(s)
                    for hyp in sorted(hyps):
                        for value in sorted(values):
                            header.append("{}_{}_{}".format(str_step, hyp, value))
                    for value in sorted(total_values):
                        header.append("{}_{}".format(str_step, value))
                header.append("total_score")
                results.writerow(header)
            row = [code]
            for s in range(steps):
                str_step = "step_{}".format(s)
                step = data["ux"].get(str_step)
                for hyp in sorted(hyps):
                    for value in sorted(values):
                        x = step[template][hyp][value] if step and step[template].get(hyp) else None
                        row.append(x)
                for value in sorted(total_values):
                    x = step["total"][value] if step else None
                    row.append(x)
            row.append(data["ux"]["total"]["score"])
        else:
            pass
        results.writerow(row)


