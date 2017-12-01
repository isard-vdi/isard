$(document).ready(function() {
    
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
				{ "data": "className"},
				{ "data": "size"},
                { "data": "net_rw"},
                { "data": "disk_rw"}],
			 "order": [[3, 'desc']],
			 "columnDefs": [ {
							"targets": 3,
							"render": function ( data, type, full, meta ) {
							  return full.size+'%';
							}},
                            {
							"targets": 4,
							"render": function ( data, type, full, meta ) {
							  return full.net_rw+'B/s';
							}},
                            {
							"targets": 5,
							"render": function ( data, type, full, meta ) {
							  return full.size+'B/s';
							}}],
    } );

    //~ domains_table.on('search.dt', function(){
            //~ drawBubbles( {children: domains_table.rows({filter: 'applied'}).data().toArray()} );
    //~ });


    // SocketIO
    socketTableDomains = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/sio_admins');

    socketTableDomains.on('connect', function() {
        connection_done();
        socket.emit('join_rooms',['domains_status'])
        console.log('Listening admins namespace domains status');
    });

    socketTableDomains.on('connect_error', function(data) {
      connection_lost();
    });

    socketTableDomains.on('desktop_status', function(data){
	  var data = JSON.parse(data);
      console.log(getDataSet(data))
      dtUpdateInsert(domains_table[data.hyp],getDataSet(data),false)
    });
    
    socketTableDomains.on('desktop_stopped', function(data){
	  var data = JSON.parse(data);
      removeData(domains_table[data.hyp],data)
    });    

};

});

//Helpers
function getDataSet(data){
    cpu=data['status']['cpu_usage']*100
    if(cpu<0.1){
        cpu=0.1;
    }else{
        cpu=(cpu).toFixed(1);
    }
    return {id: data['id'],
            name: data['name'], 
            hyp: data['hyp_started'], 
            className: data['os'].toLowerCase().replace(/ /g,''), 
            size: cpu,
            disk_rw: (data['status']['disk_rw']['block_w_bytes_per_sec']+data['status']['disk_rw']['block_r_bytes_per_sec']).toFixed(1),
            net_rw: (data['status']['net_rw']['net_w_bytes_per_sec']+data['status']['net_rw']['net_r_bytes_per_sec']).toFixed(1),
            };
}
   
function removeData(table,data){
        var index;
        for (var x = 0;x < data.length;x++){
            //Find row index by rowId if row exists
            index = table.row('#' + data[x].id);
             
            //Update row data if existing, and invalidate for redraw
            if(index.length > 0){
                table.row(index[0]).remove();
            }
        }
    //Redraw table maintaining paging
    table.draw(false);
}
 
