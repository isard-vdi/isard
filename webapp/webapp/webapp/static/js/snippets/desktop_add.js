function modal_add_desktop_datatables(){
    modal_add_desktops.destroy()
    $('#modalAddDesktop #template').val('');
    $('#modalAddDesktop #datatables-error-status').empty()

    $('#modal_add_desktops thead th').each( function () {
        var title = $(this).text();
        if(title=='Name'){
            $(this).html( '<input type="text" placeholder="Search '+title+'" />' );
        }
    } );

    modal_add_desktops = $('#modal_add_desktops').DataTable({
            "ajax": {
                "url": "/api/v3/user/templates/allowed/all",
                "dataSrc": ""
            },

            "scrollY":        "125px",
            "scrollCollapse": true,
            "paging":         false,

            "language": {
                "loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>',
                "zeroRecords":    "No matching templates found",
                "info":           "Showing _START_ to _END_ of _TOTAL_ templates",
                "infoEmpty":      "Showing 0 to 0 of 0 templates",
                "infoFiltered":   "(filtered from _MAX_ total templates)"
            },
            "rowId": "id",
            "deferRender": true,
            "columns": [
                { "data": "name"},
                { "data": "group_name", "width": "10px"},
                { "data": "user_name"}
                ],
             "order": [[0, 'asc']],
             "pageLength": 5,
        "columnDefs": [
                            {
                            "targets": 0,
                            "render": function ( data, type, full, meta ) {
                              return renderIcon1x(full)+" "+full.name;
                            }},
                            ]
    } );

    modal_add_desktops.columns().every( function () {
        var that = this;

        $( 'input', this.header() ).on( 'keyup change', function () {
            if ( that.search() !== this.value ) {
                that
                    .search( this.value )
                    .draw();
            }
        } );
    } );





}

function initalize_modal_all_desktops_events(){
   $('#modal_add_desktops tbody').on( 'click', 'tr', function () {
        rdata=modal_add_desktops.row(this).data()
        if ( $(this).hasClass('selected') ) {
            $(this).removeClass('selected');
            $('#modal_add_desktops').closest('.x_panel').addClass('datatables-error');
            $('#modalAddDesktop #datatables-error-status').html('No template selected').addClass('my-error');

            $('#modalAddDesktop #template').val('');
            $('#modalAddDesktop #btn-hardware').hide();
            $('#modalAddDesktop #hardware-block').hide();
        }
        else {
            modal_add_desktops.$('tr.selected').removeClass('selected');
            $(this).addClass('selected');
            $('#modal_add_desktops').closest('.x_panel').removeClass('datatables-error');
            $('#modalAddDesktop #datatables-error-status').empty().html('<b style="color:DarkSeaGreen">Template selected: '+rdata['name']+'</b>').removeClass('my-error');
            $('#modalAddDesktop #template').val(rdata['id']);
            //if(user['role']!='user'){
                $('#modalAddDesktop #btn-hardware').show();
                setHardwareDomainIdDefaults('#modalAddDesktop',rdata['id'])
            //}
        }
    } );

    $("#modalAddDesktop #send").on('click', function(e){
        var form = $('#modalAdd');

        form.parsley().validate();

        if (form.parsley().isValid()){
            template=$('#modalAddDesktop #template').val();
            if (template !=''){
                data=$('#modalAdd').serializeObject();
                socket.emit('domain_add',data)
            }else{
                $('#modal_add_desktops').closest('.x_panel').addClass('datatables-error');
                $('#modalAddDesktop #datatables-error-status').html('No template selected').addClass('my-error');
            }
        }
    });

        $("#modalAddDesktop #btn-hardware").on('click', function(e){
                $('#modalAddDesktop #hardware-block').show();
        });



    $("#modalTemplateDesktop #send").on('click', function(e){
            var form = $('#modalTemplateDesktopForm');

            form.parsley().validate();

            if (form.parsley().isValid()){
                desktop_id=$('#modalTemplateDesktopForm #id').val();
                if (desktop_id !=''){
                    data=$('#modalTemplateDesktopForm').serializeObject();
                    data=replaceMedia_arrays('#modalTemplateDesktopForm',data);
                    data=replaceAlloweds_arrays('#modalTemplateDesktopForm #alloweds-add',data)
                    socket.emit('domain_template_add',data)
                }else{
                    $('#modal_add_desktops').closest('.x_panel').addClass('datatables-error');
                    $('#modalAddDesktop #datatables-error-status').html('No template selected').addClass('my-error');
                }
            }
        });


}

function modal_edit_desktop_datatables(id){
    $.ajax({
        type: "GET",
        url:"/api/v3/domain/info/" + id,
        success: function(data)
        {
            $('#modalEditDesktop #forced_hyp').closest("div").remove();
            $('#modalEditDesktop #name_hidden').val(data.name);
            $('#modalEditDesktop #name').val(data.name);
            $('#modalEditDesktop #description').val(data.description);
            $('#modalEditDesktop #id').val(data.id);
            setHardwareDomainDefaults('#modalEditDesktop', data);
            if(data['guest_properties']['fullscreen']){
                $('#modalEditDesktop #guest_properties-fullscreen').iCheck('check');
            }
        }
    });
}

function icon1x(name){
    if(name=='windows' || name=='linux'){
        return "<i class='fa fa-"+name+"'></i>";
     }else{
         return "<span class='fl-"+name+"'></span>";
     }
}

function renderIcon1x(data){
    return '<span class="xe-icon" data-pk="'+data.id+'">'+icon1x(data.icon)+'</span>'
}
