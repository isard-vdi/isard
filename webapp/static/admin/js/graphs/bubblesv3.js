  // D3 Bubble Chart 
	var diameter = 500;
	var svg = d3.select('#chart').append('svg')
		.attr('width', diameter)
		.attr('height', diameter);

//~ var rect = document.querySelector ('#chart').getBoundingClientRect(),
       //~ width = height = diameter = rect.width;
//~ var svg = d3.select("#chart").append("svg")
            //~ .attr("width",width)
            //~ .attr("height",height)
            //~ .attr("transform", "translate(" + (width / 2 + 40) + "," + (height / 2 + 90) + ")");
    //~ var diameter=width
    
$(document).ready(function() {
    domains_table= $('#table-list').DataTable({
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
			},
			"rowId": "id",
            //~ "iDisplayLength": 2,
			"columns": [
				{ "data": "hyp_started" },
                { "data": "name"},
				{ "data": "className"},
				{ "data": "cpu"},
                { "data": "net_rw"},
                { "data": "disk_rw"}],
			 "order": [[3, 'desc']],
			 "columnDefs": [ {
							"targets": 3,
							"render": function ( data, type, full, meta ) {
							  return full.cpu+'%';
							}},
                            {
							"targets": 4,
							"render": function ( data, type, full, meta ) {
							  return full.net_rw+'B/s';
							}},
                            {
							"targets": 5,
							"render": function ( data, type, full, meta ) {
							  return full.disk_rw+'B/s';
							}}],
    } );

    domains_table.on('search.dt', function(){
            //~ console.log(domains_table.rows({ filter: 'applied'}).data());
            drawBubbles( {children: domains_table.rows({filter: 'applied'}).data().toArray()} );
    });


    // SocketIO
    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/sio_admins');

    socket.on('connect', function() {
        connection_done();
        socket.emit('join_rooms',['domains_stats'])
        console.log('Listening domains_stats namespace');
    });

    socket.on('connect_error', function(data) {
      connection_lost();
    });

    socket.on('domain_stats', function(data){
	  var data = JSON.parse(data);
      data['className']= data['os'].toLowerCase().replace(/ /g,''), 
      dtUpdateInsert(domains_table,data,false)
      drawBubbles( {children: domains_table.rows({filter: 'applied'}).data().toArray()} );
    });

    socket.on('domain_stats_started', function(data){
	  var data = JSON.parse(data);
      //~ data['className']= data['os'].toLowerCase().replace(/ /g,''), 
      //~ data['size']= data['cpu'],
      data['className']= data['os'].toLowerCase().replace(/ /g,''), 
      dtUpdateInsert(domains_table,data,false)
      drawBubbles( {children: domains_table.rows({filter: 'applied'}).data().toArray()} );
    });    
        
    socket.on('domain_stats_stopped', function(data){
	  var data = JSON.parse(data);
      var row = domains_table.row('#'+data.id).remove().draw();
      drawBubbles( {children: domains_table.rows({filter: 'applied'}).data().toArray()} );
    });    

});


// Bubbles
function drawBubbles(m) {

	var bubble = d3.layout.pack()
		.size([diameter, diameter])
		.value(function(d) {return d.cpu;}) // new data is loaded to bubble layout
		.padding(3);
        var nodes = bubble.nodes(m)
			.filter(function(d) { return !d.children; }); // filter out the outer bubble
		// assign new data to existing DOM 
		var vis = svg.selectAll('circle')
			.data(nodes, function(d) { return d.id; })
		var duration = 300;
		var delay = 0;
		// update - this is created before enter.append. it only applies to updating nodes.
		vis.transition()
			.duration(duration)
			.delay(function(d, i) {delay = i * 7; return delay;}) 
			.attr('transform', function(d) { return 'translate(' + d.x + ',' + d.y + ')'; })
			.attr('r', function(d) { return d.r; })
			.style('opacity', 1); // force to 1, so they don't get stuck below 1 at enter()
		// enter - only applies to incoming elements (once emptying data)	
		vis.enter().append('circle')
			.attr('transform', function(d) { return 'translate(' + d.x + ',' + d.y + ')'; })
			.attr('r', function(d) { return d.r; })
			.attr('class', function(d) { return d.className; })
			.transition()
			.duration(duration * 1.2)
			.style('opacity', 1);
		vis.append("svg:title").text(function(d) { return d.name; });
		// exit
		vis.exit()
			.transition()
			.duration(duration + delay)
			.style('opacity', 0)
			.remove();
    }


//Helpers
//~ function getInitialDataSet(data){
    //~ data['className']=data['os'].toLowerCase().replace(/ /g,'')
    //~ return {id: data['id'],
            //~ name: data['name'], 
            //~ hyp: data['hyp_started'],
            //~ os: data['os'], 
            //~ className: data['os'].toLowerCase().replace(/ /g,''), 
            //~ cpu: 100,
            //~ disk_rw: 0,
            //~ net_rw: 0,
            //~ };
//~ }

//~ function getDataSet(data){
    //~ cpu=data['status']['cpu_usage']*100
    //~ if(cpu<0.1){
        //~ cpu=0.1;
    //~ }else{
        //~ cpu=(cpu).toFixed(1);
    //~ }
    //~ return {id: data['id'],
            //~ name: data['name'], 
            //~ hyp: data['hyp_started'], 
            //~ className: data['os'].toLowerCase().replace(/ /g,''), 
            //~ size: cpu,
            //~ disk_rw: (data['status']['disk_rw']['block_w_bytes_per_sec']+data['status']['disk_rw']['block_r_bytes_per_sec']).toFixed(1),
            //~ net_rw: (data['status']['net_rw']['net_w_bytes_per_sec']+data['status']['net_rw']['net_r_bytes_per_sec']).toFixed(1),
            //~ };
//~ }
    
//~ function applyData(table, data, append){
    //~ //Quickly appends new data rows.  Does not update rows
    //~ if(append == true){
        //~ table.rows.add(data);
         
    //~ //Locate and update rows by rowId or add if new
    //~ }else{
        //~ var index;
        //~ for (var x = 0;x < data.length;x++){
            //~ //Find row index by rowId if row exists
            //~ index = table.row('#' + data[x].id);
             
            //~ //Update row data if existing, and invalidate for redraw
            //~ if(index.length > 0){
                //~ table.row(index[0]).data(data[x]).invalidate();
             
            //~ //Add row data if new
            //~ }else{
                //~ table.row.add(data[x]);
            //~ }
        //~ }
    //~ }
 
    //~ //Redraw table maintaining paging
    //~ table.draw(false);
//~ }

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
