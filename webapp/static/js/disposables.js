/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$(document).ready(function() {

    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/sio_disposables');
     
    socket.on('connect', function() {
        //~ connection_done();
        //~ socket.emit('join_client',['domains'])
        console.log('Listening disposables namespace');
    });

    socket.on('connect_error', function(data) {
      //~ connection_lost();
    });


    socket.on('disposable_data', function(data){
        var data = JSON.parse(data);
        console.log('new_data')
        console.log(data)
        

                                                //~ var url = '/desktops/download_viewer/'+getOS()+'/'+data['id'];
                                                //~ var anchor = document.createElement('a');
                                                    //~ anchor.setAttribute('href', url);
                                                    //~ anchor.setAttribute('download', 'console.vv');
                                                //~ var ev = document.createEvent("MouseEvents");
                                                    //~ ev.initMouseEvent("click", true, false, self, 0, 0, 0, 0, 0, false, false, false, false, 0, null);
                                                    //~ anchor.dispatchEvent(ev);    
                                                    
                                                    
        
        //~ dtUpdateInsert(table,data,false);
        //~ setDesktopDetailButtonsStatus(data.id, data.status);
    });
    
    //~ socket.on('desktop_delete', function(data){
        //~ var data = JSON.parse(data);
        //~ var row = table.row('#'+data.id).remove().draw();
        //~ new PNotify({
                //~ title: "Desktop deleted",
                //~ text: "Desktop "+data.name+" has been deleted",
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
    
});


	
//~ // SERVER SENT EVENTS Stream
	//~ if (!!window.EventSource) {
	  //~ var disposable_source = new EventSource('/stream/disposable');
      //~ console.log('Listening disposable...');
	//~ } else {
	  //~ // Result to xhr polling :(
	//~ }

	//~ window.onbeforeunload = function(){
	  //~ disposable_source.close();
	//~ };

	//~ disposable_source.addEventListener('Started', function(e) {
	  //~ var data = JSON.parse(e.data);

				//~ if(detectXpiPlugin()){
					//~ //SPICE-XPI Plugin
					//~ api.ajax('/desktops/viewer/xpi/'+data['id'],'GET',{}).done(function(data) {
                    //~ if(data==false){
						//~ new PNotify({
						//~ title: "Display error",
							//~ text: "Can't open display, something went wrong.",
							//~ hide: true,
							//~ delay: 3000,
							//~ icon: 'fa fa-alert-sign',
							//~ opacity: 1,
							//~ type: 'error'
						//~ });
					//~ }else{
						//~ if(data.tlsport){
							//~ openTLS(data.host, data.port, data.tlsport, data.passwd, data.ca);
						//~ }else{
							//~ openTCP(data.host, data.port, data.passwd);
						//~ }
					//~ }
                //~ }); 
				//~ }else{
					//~ //Viewer .vv Download
					//~ api.ajax('/desktops/viewer/xpi/'+data['id'],'GET',{}).done(function(error) {
                    //~ if(error==false){
						//~ new PNotify({
						//~ title: "Display error",
							//~ text: "Can't download display file, something went wrong.",
							//~ hide: true,
							//~ delay: 3000,
							//~ icon: 'fa fa-alert-sign',
							//~ opacity: 1,
							//~ type: 'error'
						//~ });
					//~ }else{
						//~ var url = '/desktops/viewer/file/'+data['id'];
						//~ var anchor = document.createElement('a');
							//~ anchor.setAttribute('href', url);
							//~ anchor.setAttribute('download', 'console.vv');
						//~ var ev = document.createEvent("MouseEvents");
							//~ ev.initMouseEvent("click", true, false, self, 0, 0, 0, 0, 0, false, false, false, false, 0, null);
						//~ anchor.dispatchEvent(ev);
					//~ }
				//~ }); 
				//~ }

	//~ }, false);
    
//~ });

