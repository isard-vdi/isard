//~ domains_count={}

$(document).ready(function() {

//~ table=$('#hypervisors')

/////////////// DOMAINS STATUS EVENTS
    socket.on('domain_stats', function(data){
	  var data = JSON.parse(data);
      if($('#domains-table-'+data.hyp_started).is(':visible')){
        dtUpdateInsert(domains_table[data.hyp_started],data,false)
      }
    });

    
    socket.on('domain_stats_stopped', function(data){
	  var data = JSON.parse(data);
      //~ domainsCountUpdate(data,1)
      if($('#domains-table-'+data.hyp_started).is(':visible')){
          var row = domains_table[data.hyp_started].row('#'+data.id).remove().draw();
      }
    });
    
});

//////// DOMAINS STATUS EVENTS

domains_table={}
function tableHypervisorDomains(hyp){
    domains_table[hyp]= $('#domains-table-'+hyp).DataTable({
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
			},
			"rowId": "id",
            //~ "iDisplayLength": 2,
			"columns": [
                { "data": "name"},
				{ "data": "os"},
				{ "data": "cpu"},
                { "data": "net_rw"},
                { "data": "disk_rw"}
                //~ { "data": null}
                ],
			 "order": [[3, 'desc']],
			 "columnDefs": [{
							"targets": 2,
							"render": function ( data, type, full, meta ) {
							  return full.cpu+'%';
							}},
                            {
							"targets": 3,
							"render": function ( data, type, full, meta ) {
							  return full.net_rw+' B/s';
							}},
                            {
							"targets": 4,
							"render": function ( data, type, full, meta ) {
							  return full.disk_rw+' B/s';
							}},
                            //~ {
							//~ "targets": 5,
							//~ "render": function ( data, type, full, meta ) {
                              //~ return '<button type="button" id="btn-stop" class="btn btn-pill-left btn-danger btn-xs"><i class="fa fa-stop"></i> Stop</button>';
                            //~ }}
                            ],
    } );
}
 
