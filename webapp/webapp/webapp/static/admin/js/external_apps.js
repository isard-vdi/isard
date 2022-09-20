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
            {
                "data": null,
                "width": "35px",
                "defaultContent": ""
            }
        ],
        "columnDefs": [{
            "targets": 6,
            "render": function( data, type, full, meta ){
                if(!(data.id == 'isardvdi' || data.id == 'isardvdi-hypervisors')) {
                    return '<button id="btn-delete" class="btn btn-xs" type="button"  data-placement="top" ><i class="fa fa-times" style="color:darkred"></i></button>'
                }
                return data;
            }
        }]
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

    $('#externalapps tbody').on('click', 'button', function(){
        var id = table.row($(this).parents('tr')).data()["id"];
        switch($(this).attr('id')){
            case 'btn-delete':
                new PNotify({
                    title: 'Delete external app',
                    text: "Are you sure you want to delete secret " + id + "?",
                    hide: false,
                    opacity: 0.9,
                    confirm: {
                        confirm: true
                    },
                    buttons: {
                        closer: false,
                        sticker: false
                    },
                    history: {
                        history: false
                    },
                    addclass: 'pnotify-center'
                }).get().on('pnotify.confirm', function() {
                    $.ajax({ 
                        type: "DELETE",
                        url: "/api/v3/admin/secret/" + id,
                    });
                    table.ajax.reload()
                }).on('pnotify.cancel', function() {});
                break;
        }
    });
});

function setModalUser(){
    $.ajax({
        type: "POST",
        url: "/api/v3/admin/userschema",
        data: '',
        contentType: "application/json",
        async: false,
        cache: false
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
