/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$(document).ready(function(){
    var table=$('#externalapps').DataTable({
        "ajax": {
            "url": "/admin/table/secrets",
            "dataSrc": "",
            "type" : "POST",
            "data": function(d){return JSON.stringify({})}
        },
        "language": {
            "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
        },
        "columns": [
            { "data": "id"},
            { "data": "secret"},
            { "data": "description"},
            { "data": "role_id"},
            { "data": "category_id"},
            { "data": "domain"},
        ]
    });

    $('.btn-new-secret').off('click').on('click', function(){
        var pk=$(this).closest("div").attr("data-pk");

        $('#modalAddSecretForm')[0].reset();

        $('#modalAddSecret').modal({
            backdrop: 'static',
            keyboard: false
        }).modal('show');

        setModalUser();

        $("#modalAddSecret #send").off('click').on('click', function(e){
            var form = $('#modalAddSecretForm');
            form.parsley().validate();
            if (form.parsley().isValid()){
                data=$('#modalAddSecretForm').serializeObject();
                data = form.serializeObject();
                data=JSON.unflatten(data);
                var notice = new PNotify({
                    text: 'Creating secret...',
                    hide: false,
                    opacity: 1,
                    icon: 'fa fa-spinner fa-pulse'
                })
                $.ajax({
                    type: "POST",
                    url:"/api/v3/admin/secret",
                    data: JSON.stringify({
                        "id": data["name"],
                        "description": data["description"],
                        "domain": data["domain"],
                        "role_id": data["role"],
                        "category_id": data["category"]
                    }),
                    contentType: "application/json",
                    success: function(data){
                        $('form').each(function() { this.reset() });
                        $('.modal').modal('hide');
                        table.ajax.reload()
                        notice.update({
                            title: "Created",
                            text: 'Secret created successfully',
                            hide: true,
                            delay: 2000,
                            icon: 'fa fa-' + data.icon,
                            opacity: 1,
                            type: 'success'
                        });
                    },
                    error: function(data){
                        notice.update({
                            title: 'ERROR',
                            text: data.responseJSON.description,
                            type: 'error',
                            hide: true,
                            icon: 'fa fa-warning',
                            delay: 5000,
                            opacity: 1
                        });
                    }
                });
            }
        });
    })
});

function setModalUser(){
    $.ajax({
        type: "POST",
        url: "/api/v3/admin/userschema",
        data: '',
        contentType: "application/json"
    }).done(function (d) {
        $.each(d, function (key, value) {
            $("." + key).find('option').remove().end();
            for(var i in d[key]){
                if(value[i].id!='disposables' && value[i].id!='eval'){
                    $("."+key).append('<option value=' + value[i].id + '>' + value[i].name + '</option>');
                }
            }
            $("."+key+' option[value="local"]').prop("selected",true);
        });
        $('#add-category').trigger("change")
    });
}
