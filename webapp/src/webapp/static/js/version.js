$.ajax({
    type: "GET",
    url: "/api/v4/admin/item/version",
    success: function (data) {
        var releaseUrl = "http://gitlab.com/isard/isardvdi/-/releases/v" + data.isardvdi_version.split(" ")[0]
        $("#version").text(data.isardvdi_version).prop("href", releaseUrl)
        if (data.commit) {
            $("#commit").text(data.commit).prop("href", "https://gitlab.com/isard/isardvdi/-/commit/" + data.commit)
            $("#commit-wrapper").show()
        }
    }
})
