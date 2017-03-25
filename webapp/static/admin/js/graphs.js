(function() { 
	
  // D3 Bubble Chart 

	var diameter = 600;

	var svg = d3.select('#chart').append('svg')
		.attr('width', diameter)
		.attr('height', diameter);

	var bubble = d3.layout.pack()
		.size([diameter, diameter])
		.value(function(d) {return d.size;}) // new data is loaded to bubble layout
		.padding(3);

	function drawBubbles(m) {

		// generate data with calculated layout values
		//~ var nodes = bubble.nodes(processData(m))
        var nodes = bubble.nodes(m)
			.filter(function(d) { return !d.children; }); // filter out the outer bubble

		// assign new data to existing DOM 
		var vis = svg.selectAll('circle')
			.data(nodes, function(d) { return d.name; })

		var visout = svg.selectAll('circleout')
			.data(nodes, function(d) { return d.name; })
            //~ .text(function(d) {
              //~ return d.name
            //~ })
            //~ .attr({
              //~ "text-anchor": "middle",
              //~ "font-size": function(d) {
                //~ return d.r / ((d.r * 8) / 100);
            //~ }});
            
  //~ .on("mouseover", function(d) {
    //~ tooltip.text(d.name + ": $" + d.hyp);
    //~ tooltip.style("visibility", "visible");
  //~ })
  //~ .on("mousemove", function() {
    //~ return tooltip.style("top", (d3.event.pageY-10)+"px").style("left",(d3.event.pageX+10)+"px");
  //~ })
  //~ .on("mouseout", function(){return tooltip.style("visibility", "hidden");});  

		// enter data -> remove, so non-exist selections for upcoming data won't stay -> enter new data -> ...

		// To chain transitions, 
		// create the transition on the updating elements before the entering elements 
		// because enter.append merges entering elements into the update selection

		var duration = 300;
		var delay = 0;


//~ var tooltip = d3.select("body")
  //~ .append("div")
  //~ .style("position", "absolute")
  //~ .style("z-index", "10")
  //~ .style("visibility", "hidden")
  //~ .style("color", "white")
  //~ .style("padding", "8px")
  //~ .style("background-color", "rgba(0, 0, 0, 0.75)")
  //~ .style("border-radius", "6px")
  //~ .style("font", "12px sans-serif")
  //~ .text("tooltip");
  
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
			.style('opacity', 0) 
			.transition()
			.duration(duration * 1.2)
			.style('opacity', 1);
            
		visout.enter().append('circleout')
			.attr('transform', function(d) { return 'translate(' + d.x + ',' + d.y + ')'; })
			.attr('r', function(d) { return d.r+d.r/10; })
			.attr('class', function(d) { return d.hyp; })
			.style('opacity', 0) 
			.transition()
			.duration(duration * 1.2)
			.style('opacity', 1);
        vis.append("svg:title").text(function(d) { return d.name; });
          //~ vis.enter().append("text")
            //~ .text(function(d) {
              //~ return d.name
            //~ })
            //~ .attr('transform', function(d) { return 'translate(' + d.x + ',' + d.y + ')'; })
            //~ .attr({
              //~ "text-anchor": "middle",
              //~ "font-size": function(d) {
                //~ return d.r / ((d.r * 8) / 100);
              //~ }
            //~ });
                        
		// exit
		vis.exit()
			.transition()
			.duration(duration + delay)
			.style('opacity', 0)
			.remove();
        



  /* Server Sent Event */


}

	if (!!window.EventSource) {
	  var source = new EventSource('/admin/graphs/d3_bubble');
	} else {
	  // Result to xhr polling :(
	}

	window.onbeforeunload = function(){
	  source.close();
	};

	source.addEventListener('update', function(e) {
	  var data = JSON.parse(e.data);
      //~ console.log(data);
    var newDataSet = [];
      for(var prop in data){
          //~ console.log(prop+' - '+data[prop]['load']);
          console.log(prop);
          newDataSet.push({name: prop, hyp: data[prop]['hyp'], className: data[prop]['icon'].toLowerCase().replace(/ /g,''), size: data[prop]['load']*100});
      }
      drawBubbles( {children: newDataSet} );
	  //~ console.log(data.id);
	  //~ setUp(data.id);
	}, false);
    
	//~ function getData() {
		//~ var i = 0;
		//~ pubnub.subscribe({
			//~ channel: channel,
			//~ callback: function(m) {
        //~ //ah too much data! I just reduce it to 1/10!
				//~ i++; 
				//~ if(i === 1 || i%10 === 0) {
					//~ drawBubbles(m);
				//~ }		
			//~ }
		//~ });
	//~ }

	//~ function processData(data) {
		//~ if(!data) return;

		//~ var obj = data.countries_msg_vol;
		//~ var newDataSet = [];
		//~ for(var prop in obj) {
            //~ console.log(prop+'-'+obj[prop]);
			//~ newDataSet.push({name: prop, className: prop.toLowerCase().replace(/ /g,''), size: obj[prop]});
		//~ }
		//~ return {children: newDataSet};
	//~ }

	//~ getData();
  
})();




//~ $(document).ready(function() {

    //~ } );


