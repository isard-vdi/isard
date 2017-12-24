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
            pass
        else:
            pass
        results.writerow(row)


