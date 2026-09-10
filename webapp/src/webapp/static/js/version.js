$.ajax({
    type: "GET",
    url:"/api/v4",
    success: function (data) {
        var isardvdi_version = data.isardvdi_version.split(" ");
        var releaseUrl = "http://gitlab.com/isard/isardvdi/-/releases/v" + data.isardvdi_version.split(" ")[0]
        $("#version").text(data.isardvdi_version).prop("href", releaseUrl)
    }
})