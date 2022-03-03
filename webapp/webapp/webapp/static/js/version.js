$.ajax({
    type: "GET",
    url:"/api/v3/",
    success: function (data) {
        var isardvdi_version = data.isardvdi_version.split(" ");
        $("#versplit").text(isardvdi_version[0]);
    }
})