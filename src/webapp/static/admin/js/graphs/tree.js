    // SocketIO
    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/sio_admins');
     
    socket.on('connect', function() {
        connection_done();
        console.log('Listening admins namespace');
    });

api.ajax('/admin/graphs_data_tree_list','GET','').done(function(data) {
    //~ socket.on('get_tree_list', function(data) {
    treeData=listToTree(data)
    //~ console.log(JSON.stringify(treeData, null, 4))

// Set the dimensions and margins of the diagram
var rect = document.querySelector ('#chart').getBoundingClientRect();
       width = height = diameter = rect.width;
var margin = {top: 20, right: 90, bottom: 30, left: 90},
    width = width - margin.left - margin.right,
    height = width - margin.top - margin.bottom;
    height=height*2

// append the svg object to the body of the page
// appends a 'group' element to 'svg'
// moves the 'group' element to the top left margin
svg = d3.select("#chart").append("svg")
    .attr("width", width + margin.right + margin.left)
    .attr("height", height + margin.top + margin.bottom)
  .append("g")
    .attr("transform", "translate("
          + margin.left + "," + margin.top + ")");

i = 0
duration = 750
root=[];

// declares a tree layout and assigns the size
treemap = d3.tree().size([height, width]);

// Assigns parent, children, height, depth
root = d3.hierarchy(treeData, function(d) { return d.children; });
root.x0 = height / 2;
root.y0 = 0;
//~ console.log(JSON.stringify(root, null, 4))
// Collapse after the second level
root.children.forEach(collapse);
//~ console.log('colapsed')
update(root);

});


// Collapse the node and all it's children
function collapse(d) {
  if(d.children) {
    d._children = d.children
    d._children.forEach(collapse)
    d.children = null
  }
}


function update(source) {

  // Assigns the x and y position for the nodes
  var treeData = treemap(root);

  // Compute the new tree layout.
  var nodes = treeData.descendants(),
      links = treeData.descendants().slice(1);

  // Normalize for fixed-depth.
  nodes.forEach(function(d){ d.y = d.depth * 180});

  // ****************** Nodes section ***************************

  // Update the nodes...
  var node = svg.selectAll('g.node')
      .data(nodes, function(d) {return d.id || (d.id = ++i); });

  // Enter any new modes at the parent's previous position.
  var nodeEnter = node.enter().append('g')
      .attr('class', 'node')
      .attr("transform", function(d) {
        return "translate(" + source.y0 + "," + source.x0 + ")";
    })
    .on('click', click);

  // Add Circle for the nodes
  nodeEnter.append('circle')
      .attr('class', 'node')
      .attr('r', 1e-6)
      .style("fill", function(d) {
          return d._children ? "lightsteelblue" : "#fff";
      });

  // Add labels for the nodes
  nodeEnter.append('text')
      .attr("dy", ".35em")
      .attr("x", function(d) {
          return d.data.kind=='desktop' ? 13 : -13;
          //~ return d.children || d._children ? -13 : 13;
      })
      .attr("text-anchor", function(d) {
          return d.data.kind=='desktop' ? 'start' : 'end';
          //~ return d.children || d._children ? "end" : "start";
      })
      .attr('class', function(d) {
          //~ console.log(d.data.kind)
          return 'node-'+d.data.kind;
          //~ if (d.data.kind=='desktop') {
              //~ return 'white';
          //~ }else{
                //~ if (d.data.kind=='menu') {
                    //~ return 'black';
                //~ }else{
                    //~ return 'yellow';
                //~ }
          //~ }
          
          //~ return d.data.kind=='desktop' ? 'white' : return d.data.kind=='menu' ? 'black' : 'yellow';
      })
      .text(function(d) { return d.data.name+':'+d.data.children.length; });

      
  // UPDATE
  var nodeUpdate = nodeEnter.merge(node);

  // Transition to the proper position for the node
  nodeUpdate.transition()
    .duration(duration)
    .attr("transform", function(d) { 
        return "translate(" + d.y + "," + d.x + ")";
     });

  // Update the node attributes and style
  nodeUpdate.select('circle.node')
    .attr('r', 10)
    .style("fill", function(d) {
        return d._children ? "lightsteelblue" : "#fff";
    })
    .attr('cursor', 'pointer');

  // Remove any exiting nodes
  var nodeExit = node.exit().transition()
      .duration(duration)
      .attr("transform", function(d) {
          return "translate(" + source.y + "," + source.x + ")";
      })
      .remove();

  // On exit reduce the node circles size to 0
  nodeExit.select('circle')
    .attr('r', 1e-6);

  // On exit reduce the opacity of text labels
  nodeExit.select('text')
    .style('fill-opacity', 1e-6);

  // ****************** links section ***************************

  // Update the links...
  var link = svg.selectAll('path.link')
      .data(links, function(d) { return d.id; });

  // Enter any new links at the parent's previous position.
  var linkEnter = link.enter().insert('path', "g")
      .attr("class", "link")
      .attr('d', function(d){
        var o = {x: source.x0, y: source.y0}
        return diagonal(o, o)
      });

  // UPDATE
  var linkUpdate = linkEnter.merge(link);

  // Transition back to the parent element position
  linkUpdate.transition()
      .duration(duration)
      .attr('d', function(d){ return diagonal(d, d.parent) });

  // Remove any exiting links
  var linkExit = link.exit().transition()
      .duration(duration)
      .attr('d', function(d) {
        var o = {x: source.x, y: source.y}
        return diagonal(o, o)
      })
      .remove();

  // Store the old positions for transition.
  nodes.forEach(function(d){
    d.x0 = d.x;
    d.y0 = d.y;
  });

  // Creates a curved (diagonal) path from parent to the child nodes
  function diagonal(s, d) {

    path = 'M ${s.y} ${s.x} \
            C ${(s.y + d.y) / 2} ${s.x}, \
              ${(s.y + d.y) / 2} ${d.x}, \
              ${d.y} ${d.x}'

    return path
  }

  // Toggle children on click.
  function click(d) {
    if (d.children) {
        d._children = d.children;
        d.children = null;
      } else {
        d.children = d._children;
        d._children = null;
      }
    update(d);
  }
}


//~ function getNestedChildren(arr, parent) {
    //~ var out = []
    //~ for(var i in arr) {
        //~ if(arr[i].parent == parent) {
            //~ var children = getNestedChildren(arr, arr[i].id)

            //~ if(children.length) {
                //~ arr[i].children = children
            //~ }
            //~ out.push(arr[i])
        //~ }
    //~ }
    //~ return out
//~ }

function listToTree(data) {
  var ID_KEY = 'id';
  var PARENT_KEY = 'parent';
  var CHILDREN_KEY = 'children';
  
  var item, id, parentId;
  var map = {};
	for(var i = 0; i < data.length; i++ ) { 
  	if(data[i][ID_KEY]){
    	map[data[i][ID_KEY]] = data[i];
      data[i][CHILDREN_KEY] = [];
    }
  }
  for (var i = 0; i < data.length; i++) {
    if(data[i][PARENT_KEY]) { // is a child
    	if(map[data[i][PARENT_KEY]]) // for dirty data
      {
    		map[data[i][PARENT_KEY]][CHILDREN_KEY].push(data[i]); // add child to parent
    		data.splice( i, 1 ); // remove from root
      	i--; // iterator correction
      } else {
      	data[i][PARENT_KEY] = 0; // clean dirty data
      }
    }
  };
  //~ console.log(JSON.stringify(data[0], null, 4))
  return data[0];
}







