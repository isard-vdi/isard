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
      applyData(domains_table,getDataSet(data),false)
      //~ drawBubbles( {children: domains_table.rows({filter: 'applied'}).data().toArray()} );
        //~ myBubbleChart('#chart', d3FormatData(data));
        chart('#chart', d3FormatData(data));
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
    
function applyData(table, data, append){
    //Quickly appends new data rows.  Does not update rows
    if(append == true){
        table.rows.add(data);
         
    //Locate and update rows by rowId or add if new
    }else{
        var index;
        for (var x = 0;x < data.length;x++){
            //Find row index by rowId if row exists
            index = table.row('#' + data[x].id);
             
            //Update row data if existing, and invalidate for redraw
            if(index.length > 0){
                table.row(index[0]).data(data[x]).invalidate();
             
            //Add row data if new
            }else{
                table.row.add(data[x]);
            }
        }
    }
 
    //Redraw table maintaining paging
    table.draw(false);
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


/* bubbleChart creation function. Returns a function that will
 * instantiate a new bubble chart given a DOM element to display
 * it in and a dataset to visualize.
 *
 * Organization and style inspired by:
 * https://bost.ocks.org/mike/chart/
 *
 */
function bubbleChart() {
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

  // Charge function that is called for each node.
  // As part of the ManyBody force.
  // This is what creates the repulsion between nodes.
  //
  // Charge is proportional to the diameter of the
  // circle (which is stored in the radius attribute
  // of the circle's associated data.
  //
  // This is done to allow for accurate collision
  // detection with nodes of different sizes.
  //
  // Charge is negative because we want nodes to repel.
  // @v4 Before the charge was a stand-alone attribute
  //  of the force layout. Now we can use it as a separate force!
  function charge(d) {
    return -Math.pow(d.radius, 2.0) * forceStrength;
  }

  // Here we create a force layout and
  // @v4 We create a force simulation now and
  //  add forces to it.
  var simulation = d3.forceSimulation()
    .velocityDecay(0.2)
    .force('x', d3.forceX().strength(forceStrength).x(center.x))
    .force('y', d3.forceY().strength(forceStrength).y(center.y))
    .force('charge', d3.forceManyBody().strength(charge))
    .on('tick', ticked);

  // @v4 Force starts up automatically,
  //  which we don't want as there aren't any nodes yet.
  simulation.stop();

  // Nice looking colors - no reason to buck the trend
  // @v4 scales now have a flattened naming scheme
  var fillColor = d3.scaleOrdinal()
    .domain(['low', 'medium', 'high'])
    .range(['#d84b2a', '#beccae', '#7aa25c']);


  /*
   * This data manipulation function takes the raw data from
   * the CSV file and converts it into an array of node objects.
   * Each node will store data and visualization values to visualize
   * a bubble.
   *
   * rawData is expected to be an array of data objects, read in from
   * one of d3's loading functions like d3.csv.
   *
   * This function returns the new node array, with a node in that
   * array for each element in the rawData input.
   */
  function createNodes(rawData) {
    // Use the max total_amount in the data as the max in the scale's domain
    // note we have to ensure the total_amount is a number.
    var maxAmount = d3.max(rawData, function (d) { return +d.total_amount; });

    // Sizes bubbles based on area.
    // @v4: new flattened scale names.
    var radiusScale = d3.scalePow()
      .exponent(0.5)
      .range([2, 85])
      .domain([0, maxAmount]);

    // Use map() to convert raw data into node data.
    // Checkout http://learnjsdata.com/ for more on
    // working with data.
    var myNodes = rawData.map(function (d) {
        console.log( Math.random() * width)
      return {
        id: d.id,
        radius: radiusScale(+d.total_amount),
        value: +d.total_amount,
        name: d.grant_title,
        org: d.organization,
        group: d.group,
        year: d.start_year,
        x: Math.random() * width,
        y: Math.random() * height
      };
    });

    // sort them to prevent occlusion of smaller nodes.
    myNodes.sort(function (a, b) { return b.value - a.value; });

    return myNodes;
  }

  /*
   * Main entry point to the bubble chart. This function is returned
   * by the parent closure. It prepares the rawData for visualization
   * and adds an svg element to the provided selector and starts the
   * visualization creation process.
   *
   * selector is expected to be a DOM element or CSS selector that
   * points to the parent element of the bubble chart. Inside this
   * element, the code will add the SVG continer for the visualization.
   *
   * rawData is expected to be an array of data objects as provided by
   * a d3 loading function like d3.csv.
   */
  var chart = function chart(selector, rawData) {
    // convert raw data into nodes data
    nodes = createNodes(rawData);

    // Create a SVG element inside the provided selector
    // with desired size.
    //~ svg = d3.select(selector)
      //~ .append('svg')
      //~ .attr('width', width)
      //~ .attr('height', height);

    // Bind nodes data to what will become DOM elements to represent them.
    bubbles = svg.selectAll('.bubble')
      .data(nodes, function (d) { return d.id; });

    // Create new circle elements each with class `bubble`.
    // There will be one circle.bubble for each object in the nodes array.
    // Initially, their radius (r attribute) will be 0.
    // @v4 Selections are immutable, so lets capture the
    //  enter selection to apply our transtition to below.
    var bubblesE = bubbles.enter().append('circle')
      .classed('bubble', true)
      .attr('r', 0)
      .attr('fill', function (d) { return fillColor(d.group); })
      .attr('stroke', function (d) { return d3.rgb(fillColor(d.group)).darker(); })
      .attr('stroke-width', 2)
      //~ .on('mouseover', showDetail)
      //~ .on('mouseout', hideDetail);

    // @v4 Merge the original empty selection and the enter selection
    bubbles = bubbles.merge(bubblesE);

    // Fancy transition to make bubbles appear, ending with the
    // correct radius
    bubbles.transition()
      .duration(2000)
      .attr('r', function (d) { return d.radius; });

    // Set the simulation's nodes to our newly created nodes array.
    // @v4 Once we set the nodes, the simulation will start running automatically!
    simulation.nodes(nodes);

    // Set initial layout to single group.
    groupBubbles();
  };

  /*
   * Callback function that is called after every tick of the
   * force simulation.
   * Here we do the acutal repositioning of the SVG circles
   * based on the current x and y values of their bound node data.
   * These x and y values are modified by the force simulation.
   */
  function ticked() {
    bubbles
      .attr('cx', function (d) { return d.x; })
      .attr('cy', function (d) { return d.y; });
  }

  /*
   * Provides a x value for each node to be used with the split by year
   * x force.
   */
  function nodeYearPos(d) {
    return yearCenters[d.year].x;
  }


  /*
   * Sets visualization in "single group mode".
   * The year labels are hidden and the force layout
   * tick function is set to move all nodes to the
   * center of the visualization.
   */
  function groupBubbles() {
    hideYearTitles();

    // @v4 Reset the 'x' force to draw the bubbles to the center.
    simulation.force('x', d3.forceX().strength(forceStrength).x(center.x));

    // @v4 We can reset the alpha value and restart the simulation
    simulation.alpha(1).restart();
  }


  /*
   * Sets visualization in "split by year mode".
   * The year labels are shown and the force layout
   * tick function is set to move nodes to the
   * yearCenter of their data's year.
   */
  function splitBubbles() {
    showYearTitles();

    // @v4 Reset the 'x' force to draw the bubbles to their year centers
    simulation.force('x', d3.forceX().strength(forceStrength).x(nodeYearPos));

    // @v4 We can reset the alpha value and restart the simulation
    simulation.alpha(1).restart();
  }

  /*
   * Hides Year title displays.
   */
  function hideYearTitles() {
    svg.selectAll('.year').remove();
  }

  /*
   * Shows Year title displays.
   */
  function showYearTitles() {
    // Another way to do this would be to create
    // the year texts once and then just hide them.
    var yearsData = d3.keys(yearsTitleX);
    var years = svg.selectAll('.year')
      .data(yearsData);

    years.enter().append('text')
      .attr('class', 'year')
      .attr('x', function (d) { return yearsTitleX[d]; })
      .attr('y', 40)
      .attr('text-anchor', 'middle')
      .text(function (d) { return d; });
  }


  /*
   * Function called on mouseover to display the
   * details of a bubble in the tooltip.
   */
  function showDetail(d) {
    // change outline to indicate hover state.
    d3.select(this).attr('stroke', 'black');

    var content = '<span class="name">Title: </span><span class="value">' +
                  d.name +
                  '</span><br/>' +
                  '<span class="name">Amount: </span><span class="value">$' +
                  addCommas(d.value) +
                  '</span><br/>' +
                  '<span class="name">Year: </span><span class="value">' +
                  d.year +
                  '</span>';

    tooltip.showTooltip(content, d3.event);
  }

  /*
   * Hides tooltip
   */
  function hideDetail(d) {
    // reset outline
    d3.select(this)
      .attr('stroke', d3.rgb(fillColor(d.group)).darker());

    tooltip.hideTooltip();
  }

  /*
   * Externally accessible function (this is attached to the
   * returned chart function). Allows the visualization to toggle
   * between "single group" and "split by year" modes.
   *
   * displayName is expected to be a string and either 'year' or 'all'.
   */
  chart.toggleDisplay = function (displayName) {
    if (displayName === 'year') {
      splitBubbles();
    } else {
      groupBubbles();
    }
  };


  // return the chart function from closure.
  return chart;
}

/*
 * Below is the initialization code as well as some helper functions
 * to create a new bubble chart instance, load the data, and display it.
 */

var myBubbleChart = bubbleChart();

/*
 * Function called once data is loaded from CSV.
 * Calls bubble chart function to display inside #vis div.
 */
function display(error, data) {
  if (error) {
    console.log(error);
  }

  myBubbleChart('#chart', data);
}

/*
 * Sets up the layout buttons to allow for toggling between view modes.
 */
function setupButtons() {
  d3.select('#toolbar')
    .selectAll('.button')
    .on('click', function () {
      // Remove active class from all buttons
      d3.selectAll('.button').classed('active', false);
      // Find the button just clicked
      var button = d3.select(this);

      // Set it as the active button
      button.classed('active', true);

      // Get the id of the button
      var buttonId = button.attr('id');

      // Toggle the bubble chart based on
      // the currently clicked button.
      myBubbleChart.toggleDisplay(buttonId);
    });
}

/*
 * Helper function to convert a number into a string
 * and add commas to it to improve presentation.
 */
function addCommas(nStr) {
  nStr += '';
  var x = nStr.split('.');
  var x1 = x[0];
  var x2 = x.length > 1 ? '.' + x[1] : '';
  var rgx = /(\d+)(\d{3})/;
  while (rgx.test(x1)) {
    x1 = x1.replace(rgx, '$1' + ',' + '$2');
  }

  return x1 + x2;
}

// Load the data.
//~ d3.csv('data/gates_money.csv', display);

// setup the buttons.
setupButtons();
