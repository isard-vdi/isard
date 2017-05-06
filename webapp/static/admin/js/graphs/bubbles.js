  // D3 Bubble Chart 
	//~ var diameter = 500;
	//~ var svg = d3.select('#chart').append('svg')
		//~ .attr('width', diameter)
		//~ .attr('height', diameter);

var rect = document.querySelector ('#chart').getBoundingClientRect(),
       width = height = diameter = rect.width;
var svg = d3.select("#chart").append("svg")
            .attr("width",width)
            .attr("height",height);
    //~ var diameter=width


  // Constants for sizing
  var width = 940;
  var height = 600;

  // tooltip for mouseover functionality
  var tooltip = '' //floatingTooltip('gates_tooltip', 240);

  // Locations to move bubbles towards, depending
  // on which view mode is selected.
  var center = { x: width / 2, y: height / 2 };

  var yearCenters = {
    2008: { x: width / 3, y: height / 2 },
    2009: { x: width / 2, y: height / 2 },
    2010: { x: 2 * width / 3, y: height / 2 }
  };

  // X locations of the year titles.
  var yearsTitleX = {
    2008: 160,
    2009: width / 2,
    2010: width - 160
  };

  // @v4 strength to apply to the position forces
  var forceStrength = 0.03;

  // These will be set in create_nodes and create_vis
  //~ var svg = null;
  var bubbles = null;
  var nodes = [];

$(document).ready(function() {
    domains_table= $('#table-list').DataTable({
			"language": {
				"loadingRecords": '<i class="fa fa-spinner fa-pulse fa-3x fa-fw"></i><span class="sr-only">Loading...</span>'
			},
			"rowId": "id",
            //~ "iDisplayLength": 2,
			"columns": [
				{ "data": "hyp" },
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

    domains_table.on('search.dt', function(){
            //~ console.log(domains_table.rows({ filter: 'applied'}).data());
            //~ drawBubbles( {children: domains_table.rows({filter: 'applied'}).data().toArray()} );
    });


    // SocketIO
    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/sio_admins');

    socket.on('connect', function() {
        connection_done();
        socket.emit('join_rooms',['domains_status'])
        console.log('Listening admins namespace');
    });

    socket.on('connect_error', function(data) {
      connection_lost();
    });

    socket.on('desktop_status', function(data){
	  var data = JSON.parse(data);
      console.log(data)
      dtUpdateInsert(domains_table,getDataSet(data),false)
      //~ applyData(domains_table,getDataSet(data),false)
      //~ drawBubbles( {children: domains_table.rows({filter: 'applied'}).data().toArray()} );
        //~ myBubbleChart('#chart', d3FormatData(data));
        //~ chart('#chart', d3FormatData(data));
        drawBubbles( {children: domains_table.rows({filter: 'applied'}).data().toArray()} );
    });
    
    socket.on('desktop_stopped', function(data){
	  var data = JSON.parse(data);
      removeData(domains_table,data)
      //~ drawBubbles4()
      //~ drawBubbles4( {children: domains_table.rows({filter: 'applied'}).data().toArray()} );
    });    

});



//Helpers
function getDataSet(data){
    cpu=data['status']['cpu_usage']*100
    if(cpu<0.1){
        cpu=0.1;
    }else{
        cpu=(cpu).toFixed(1);
    }
    return [{id: data['id'],
            name: data['name'], 
            hyp: data['hyp_started'], 
            className: data['os'].toLowerCase().replace(/ /g,''), 
            size: cpu,
            disk_rw: (data['status']['disk_rw']['block_w_bytes_per_sec']+data['status']['disk_rw']['block_r_bytes_per_sec']).toFixed(1),
            net_rw: (data['status']['net_rw']['net_w_bytes_per_sec']+data['status']['net_rw']['net_r_bytes_per_sec']).toFixed(1),
            }];

      //~ return {
        //~ id: d.id,
        //~ radius: radiusScale(+d.total_amount),
        //~ value: +d.total_amount,
        //~ name: d.grant_title,
        //~ org: d.organization,
        //~ group: d.group,
        //~ year: d.start_year,
        //~ x: Math.random() * 900,
        //~ y: Math.random() * 800
      //~ };

}

function d3FormatData(data){
    cpu=data['status']['cpu_usage']*100
    if(cpu<0.1){
        cpu=0.1;
    }else{
        cpu=(cpu).toFixed(1);
    }
    return [{id: data['id'],
            name: data['name'], 
            year: data['hyp_started'], 
            group: data['os'],
            organization: data['os'].toLowerCase().replace(/ /g,''), 
            total_amount: cpu*100,
            //~ disk_rw: (data['status']['disk_rw']['block_w_bytes_per_sec']+data['status']['disk_rw']['block_r_bytes_per_sec']).toFixed(1),
            //~ net_rw: (data['status']['net_rw']['net_w_bytes_per_sec']+data['status']['net_rw']['net_r_bytes_per_sec']).toFixed(1),
            }];
}
    
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


// Bubbles
function drawBubbles(m) {
    console.log(m)
	//~ var bubble = d3.layout.pack()
    var bubble = d3.pack(m)
		.size([diameter, diameter])
		//~ .value(function(d) {return d.size;}) // new data is loaded to bubble layout
		.padding(3);
        //~ var nodes = bubble.nodes(m)
			//~ .filter(function(d) { return !d.children; }); // filter out the outer bubble
		// assign new data to existing DOM 
        
    var nodes = d3.hierarchy(m)
            .sum(function(d) { return d.size; });

    //~ var node = svg.selectAll(".circle")
            //~ .data(bubble(nodes).descendants())
            //~ .enter()
            //~ .filter(function(d){
                //~ return  !d.children
            //~ })
            //~ .append("g")
            //~ .attr("class", "circle")
            //~ .attr("transform", function(d) {
                //~ return "translate(" + d.x + "," + d.y + ")";
            //~ });


    var node = svg.selectAll(".node")
            .data(bubble(nodes).descendants())
            .enter()
            .filter(function(d){
                return  !d.children
            })
            .append("g")
            .attr("class", "node")
            .attr("transform", function(d) {
                return "translate(" + d.x + "," + d.y + ")";
            });
            
node.append("title")
            .text(function(d) {
                return d.id + ": " + d.size;
            });

    node.append("circle")
            .attr("r", function(d) {
                return d.r;
            })
            .style("fill", function(d) {
                return 'cyan'; //color(d.className);
            });

    node.append("text")
            .attr("dy", ".3em")
            .style("text-anchor", "middle")
            .text(function(d) {
                return d.data.size;
            });

    d3.select(self.frameElement)
            .style("height", diameter + "px");


    }









