/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$hypervisor_pool_template = $(".hyper-pool-detail");
var tablepools;
$(document).ready(function() {

	$('#modalAddPool').on('hidden.bs.modal', function(){
        $(this).find('form')[0].reset();
        slider_avgcpu.reset()
        slider_freqcpu.reset()
        slider_freemem.reset()
        slider_iowait.reset()

    });
    //~ $('[data-dismiss=modal]').on('click', function (e) {
        //~ var $t = $(this),
            //~ target = $t[0].href || $t.data("target") || $t.parents('.modal') || [];

      //~ $(target).find('form')[0].reset();
        //~ console.log('reset-close')
        //~ slider_avgcpu.reset()
        //~ slider_freqcpu.reset()
        //~ slider_freemem.reset()
        //~ slider_iowait.reset()
    //~ })
	$('.btn-new-pool').on('click', function () {
			$('#modalAddPool').modal({
				backdrop: 'static',
				keyboard: false
			}).modal('show');
            slider_weight();
            hyper_list();
            interfaces_list();
                //~ $('.paths-tags').select2({
                    //~ tags: true,
                    //~ tokenSeparators: [",", " "]
                //~ }).on("change", function(e) {
                    //~ var isNew = $(this).find('[data-select2-tag="true"]');
                    //~ if(isNew.length){
                        //~ isNew.replaceWith('<option selected value="'+isNew.val()+'">'+isNew.val()+'</option>');
                        //~ $.ajax({
                            //~ // ... store tag ...
                        //~ });
                    //~ }
                //~ });


                
            
                $('.table_bases_add').on('click', function () {
                    $('#table_bases tbody').append('<tr>\
								<th><input name="path" placeholder="Absolute path (/isard/bases)" type="text" style="width:95%"></th>\
								<th><select name="disk_operations" class="hyper_list" placeholder="" style="width:95%"></select></th>\
								<th><input name="weight" class="form-control col-md-7 col-xs-12 weight-slider" type="text" style="width:95%"></th>\
								</tr>');

					slider_weight();
                    hyper_list();
                });

                $('#table_templates_add').on('click', function () {
                    $('#table_templates tbody').append('<tr>\
								<th><input name="path" placeholder="Absolute path (/isard/templates)" type="text" style="width:95%"></th>\
								<th><input name="disk_operations" class="hyper_list" placeholder="" type="text" style="width:95%"></th>\
								<th><input name="weight" class="form-control col-md-7 col-xs-12 weight-slider" type="text" style="width:95%"></th>\
								</tr>');

					slider_weight();
                    hyper_list();
                });

                $('#table_groups_add').on('click', function () {
                    $('#table_groups tbody').append('<tr>\
								<th><input name="path" placeholder="Absolute path (/isard/groups)" type="text" style="width:95%"></th>\
								<th><input name="disk_operations" class="hyper_list" placeholder="" type="text" style="width:95%"></th>\
								<th><input name="weight" class="form-control col-md-7 col-xs-12 weight-slider" type="text" style="width:95%"></th>\
								</tr>');

					slider_weight();
                    hyper_list();
                });

                $('#table_isos_add').on('click', function () {
                    $('#table_isos tbody').append('<tr>\
								<th><input name="path" placeholder="Absolute path (/isard/isos)" type="text" style="width:95%"></th>\
								<th><input name="disk_operations" class="hyper_list" placeholder="" type="text" style="width:95%"></th>\
								<th><input name="weight" class="form-control col-md-7 col-xs-12 weight-slider" type="text" style="width:95%"></th>\
								</tr>');

					slider_weight();
                    hyper_list();
                });
                                                            
				$("#weights-avg_cpu_idle-weight").ionRangeSlider({
						  type: "single",
						  min: 0,
						  max: 100,
                          from: 20,
                          step:5,
						  grid: true,
						  disable: false
						  }).data("ionRangeSlider").update();
                slider_avgcpu = $("#weights-avg_cpu_idle-weight").data("ionRangeSlider");
				$("#weights-cpu_freq-weight").ionRangeSlider({
						  type: "single",
						  min: 0,
						  max: 100,
                          step:5,
						  grid: true,
						  disable: false
						  }).data("ionRangeSlider").update();
                slider_freqcpu = $("#weights-cpu_freq-weight").data("ionRangeSlider");
				$("#weights-free_memory-weight").ionRangeSlider({
						  type: "single",
						  min: 0,
						  max: 100,
                          step:5,
						  grid: true,
						  disable: false
						  }).data("ionRangeSlider").update();
                slider_freemem = $("#weights-free_memory-weight").data("ionRangeSlider");
				$("#weights-io_wait_peaks-weight").ionRangeSlider({
						  type: "single",
						  min: 0,
						  max: 100,
                          step:5,
						  grid: true,
						  disable: false
						  }).data("ionRangeSlider").update();	
                slider_iowait = $("#weights-io_wait_peaks-weight").data("ionRangeSlider");

				//~ $(".weight-slider").ionRangeSlider({
						  //~ type: "single",
						  //~ min: 0,
						  //~ max: 100,
                          //~ step:5,
						  //~ grid: true,
						  //~ disable: false
						  //~ }).data("ionRangeSlider").update();	
             
	});

    $("#modalAddPool #send").on('click', function(e){
            var form = $('#modalAddHyper #modalAdd');
            //~ form.parsley().validate();
            //~ var queryString = $('#modalAdd').serialize();
            data=$('#modalAddPool #modalAdd').serializeObject();
            //~ socket.emit('hypervisor_add',data)
            //~ if (form.parsley().isValid()){
                //~ template=$('#modalAddDesktop #template').val();
                //~ console.log('TEMPLATE:'+template)
                //~ if (template !=''){
                    //~ var queryString = $('#modalAdd').serialize();
                    //~ data=$('#modalAdd').serializeObject();
                    //~ socket.emit('domain_add',data)
                //~ }else{
                    //~ $('#modal_add_desktops').closest('.x_panel').addClass('datatables-error');
                    //~ $('#modalAddDesktop #datatables-error-status').html('No template selected').addClass('my-error');
                //~ }
            //~ }
        });

    tablepools = $('#hypervisors_pools').DataTable( {
        "ajax": {
            "url": "/admin/hypervisors_pools/",
            "dataSrc": ""
        },
		"rowId": "id",
		"deferRender": false,
        "columns": [
				{
                "className":      'details-control',
                "orderable":      false,
                "data":           null,
                "width": "10px",
                "defaultContent": '<button class="btn btn-xs btn-info" type="button"  data-placement="top" ><i class="fa fa-plus"></i></button>'
				},
            { "data": "name"},
            { "data": "description"}]
    } );

	$('#hypervisors_pools').find('tbody').on('click', 'td.details-control', function () {
        var tr = $(this).closest('tr');
        var row = tablepools.row( tr );
		
        if ( row.child.isShown() ) {
            // This row is already open - close it
            row.child.hide();
            tr.removeClass('shown');
        }
        else {
            // Open this row
            row.child( formatHypervisorPool(row.data()) ).show();
            data = row.data();
			$.each( data['paths'], function( k, v) {
				$.each( data['paths'][k], function( key, val ) {
					//~ console.log(data['paths'][k])
					$('#hyper-pools-paths-'+data.id+' tbody').append('<tr><td>'+k+'</td><td>'+val['path']+'</td><td>'+val['disk_operations']+'</td><td>'+val['weight']+'</td></tr>');
				});
			});
			if(data['interfaces'].length==0){
				$('#hyper-pools-nets-'+data.id+' tbody').append('[All interfaces available for selection]')
			}else{
				$.each( data['interfaces'], function( k, v) {
					$.each( data['interfaces'][k], function( key, val ) {
						$('#hyper-pools-nets-'+data.id+' tbody').append('<tr><td>'+k+'</td><td>'+key+'</td><td>'+val['disk_operations']+'</td><td>'+val['weight']+'</td></tr>');
					});
				});
			}
            if(data['viewer']['certificate'].length >10){data['viewer']['certificate']='Yes';}
            $('#hyper-pools-viewer-'+data.id+' tbody').append('<tr><td>'+data['viewer']['defaultMode']+'</td><td>'+data['viewer']['domain']+'</td><td>'+data['viewer']['certificate']+'</td> \
                <td><button class="btn btn-xs btn-viewer-pool-edit" data-pk="'+data.id+'" type="button" ><i class="fa fa-pencil" style="color:darkblue"></i></button></td> \
                </tr>');
            tr.addClass('shown');
            
            $('.btn-viewer-pool-edit').on('click', function(){
                pk=$(this).attr("data-pk");
                //~ setHardwareDomainDefaults('#modalEditDesktop',pk);
                $("#modalEditViewer #modalEditViewerForm")[0].reset();
                $('#modalEditViewer').modal({
                    backdrop: 'static',
                    keyboard: false
                }).modal('show');
                 //~ $('#hardware-block').hide();
                //~ $('#modalEdit').parsley();
                //~ modal_edit_desktop_datatables(pk);               
            });
            
            $("#modalEditViewer #send").on('click', function(e){
                var form = $('#modalEditViewer #modalEditViewerForm');
                form.parsley().validate();
                if (form.parsley().isValid()){
                        data=$('#modalEditViewer #modalEditViewerForm').serializeObject();
                        console.log(data)
                        socket.emit('hyperpool_edit',data)
                }
            });
                    
        }
    } );



    
});// document ready




function formatHypervisorPool ( d ) {
		$newPanel = $hypervisor_pool_template.clone();
		$newPanel.html(function(i, oldHtml){
			return oldHtml.replace(/d.id/g, d.id).replace(/d.name/g, d.name);
		});
		return $newPanel
}  


function table2json(){
							var newFormData = [];
							  $('#datatable_paths tr:not(:first)').each(function(i) {
								var tb = jQuery(this);
								var obj = {};
								tb.find('input').each(function() {
								  obj[this.name] = this.value;
								});
								//~ obj['row'] = i;
								newFormData.push(obj);
							  });
							  //~ console.log(newFormData);
	
	
}

function slider_weight(){
					$(".weight-slider").ionRangeSlider({
							  type: "single",
							  min: 0,
							  max: 100,
							  step:5,
							  grid: true,
							  disable: false
							  }).data("ionRangeSlider").update();	
}

function hyper_list(){
                $('.hyper_list').select2({
                    tags: true,
                    multiple: true,
                    tokenSeparators: [',', ' '],
                    //~ minimumInputLength: 2,
                    //~ minimumResultsForSearch: 10,
                    ajax: {
                        url: "/admin/hypervisors/json",
                        dataType: "json",
                        type: "GET",
                        data: function (params) {

                            var queryParameters = {
                                term: params.term
                            }
                            return queryParameters;
                        },
                        processResults: function (data) {
                            return {
                                results: $.map(data, function (item) {
                                    return {
                                        text: item.id,
                                        id: item.id
                                    }
                                })
                            };
                        }
                    }
                });
       
}

function interfaces_list(){
                $('#interfaces').select2({
                    tags: true,
                    multiple: true,
                    tokenSeparators: [',', ' '],
                    //~ minimumInputLength: 2,
                    //~ minimumResultsForSearch: 10,
                    ajax: {
                        url: "/admin/table/interfaces/get",
                        dataType: "json",
                        type: "GET",
                        data: function (params) {

                            var queryParameters = {
                                term: params.term
                            }
                            return queryParameters;
                        },
                        processResults: function (data) {
                            return {
                                results: $.map(data, function (item) {
                                    return {
                                        text: item.name,
                                        id: item.id
                                    }
                                })
                            };
                        }
                    }
                });
       
}

