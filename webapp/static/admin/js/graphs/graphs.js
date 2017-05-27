/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/


function timestamp() { return (new Date).getTime() / 1000; }
chart={}
      
$(document).ready(function() {
	startEngineTimer();
    // SocketIO
    //~ socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/sio_admins');
     
    //~ socket.on('connect', function() {
        //~ connection_done();
        //~ socket.emit('join_rooms',['hyper'])
        //~ console.log('Listening admins namespace');
    //~ });

    //~ socket.on('connect_error', function(data) {
      //~ connection_lost();
    //~ });
    
    //~ socket.on('user_quota', function(data) {
        //~ console.log('Quota update')
        //~ var data = JSON.parse(data);
        //~ drawUserQuota(data);
    //~ });

    //~ socket.on('hyper_data', function(data){
        //~ console.log('add or update')
        //~ var data = JSON.parse(data);
		//~ if($("#" + data.id).length == 0) {
		  //~ //it doesn't exist
		  //~ table.row.add(data).draw();
		//~ }else{
          //~ //if already exists do an update (ie. connection lost and reconnect)
          //~ var row = table.row('#'+data.id); 
          //~ table.row(row).data(data).invalidate();			
		//~ }
        //~ table.draw(false);
    //~ });

    //~ socket.on('hyper_status', function(data){
        //~ var data = JSON.parse(data);
        //str = JSON.stringify(data);
        //str = JSON.stringify(data, null, 4);
        //console.log(str)
        //~ console.log('status: '+data.hyp_id)
        //~ console.log('status: '+data['cpu_percent-used'])
        //~ console.log('status: '+data['load-percent_free'])
        //~ chart[data.hyp_id].push([
          //~ { time: timestamp(), y: data['cpu_percent-used']},
          //~ { time: timestamp(), y: data['load-percent_free']}
        //~ ]);
    //~ });
        
    //~ socket.on('hyper_delete', function(data){
        //~ console.log('delete')
        //~ var data = JSON.parse(data);
        //~ var row = table.row('#'+data.id).remove().draw();
        //~ new PNotify({
                //~ title: "Hypervisor deleted",
                //~ text: "Hypervisor "+data.name+" has been deleted",
                //~ hide: true,
                //~ delay: 4000,
                //~ icon: 'fa fa-success',
                //~ opacity: 1,
                //~ type: 'success'
        //~ });
    //~ });
    
    //~ socket.on('result', function (data) {
        //~ var data = JSON.parse(data);
        //~ new PNotify({
                //~ title: data.title,
                //~ text: data.text,
                //~ hide: true,
                //~ delay: 4000,
                //~ icon: 'fa fa-'+data.icon,
                //~ opacity: 1,
                //~ type: data.type
        //~ });
    //~ });

});// document ready

function startEngineTimer() {
	var url='/admin/engine_graphs'
        ajax(url,'GET',{}).done(function(data) {
            console.log(data)

        if(data.broom_thread_is_alive){
                $('#engine_broom_circle').removeClass("bg-red")
                $('#engine_broom_circle').addClass("bg-green")
            }else{
                $('#engine_broom_circle').removeClass("bg-green")
                $('#engine_broom_circle').addClass("bg-red")
                }
        });    
    //~ document.getElementById("txt").innerHTML = h+ ":" + m + ":" + s;
    t = setTimeout(function(){ startEngineTimer() }, 10000);
}



ajax = function(uri,method, data) {
                var request = {
                    url: uri,
                    type: method,
                    contentType: "application/json",
                    accepts: "application/json",
                    cache: false,
                    dataType: 'json',
                    data: JSON.stringify(data),
                    error: function(jqXHR) {
                        console.log("ajax error " + jqXHR.status);
                    }
                };
                return $.ajax(request);
};
