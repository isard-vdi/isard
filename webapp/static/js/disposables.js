/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$(document).ready(function() {
            $('#disposable').on('change', function() {
                if(this.value!="default"){
                    socket.emit('disposables_add',{'pk':this.value}) 
                    $('#disposable').prop("disabled",true);
                    $('#disposable option[value="default"]').text(' Wait till '+$("#disposable option[value='"+this.value+"']").text()+' viewer opens...');
                    $('#disposable option[value="default"]').prop("selected",true);
                }
            })  


    socket = io.connect(location.protocol+'//' + document.domain + ':' + location.port+'/sio_disposables');
     
    socket.on('connect', function() {
        console.log('Listening disposables namespace');
    });

    socket.on('connect_error', function(data) {
      //~ connection_lost();
    });


    socket.on('disposable_data', function(data){
        var data = JSON.parse(data);
        if(data['status']=='Started'){
			$('#disposable option[value="default"]').text('Choose a desktop...');
			$('#disposable option[value="default"]').prop("selected",true);
			$('#disposable').prop("disabled",false);
			getClientViewer(data,socket)
	  }										
        
    });

    socket.on('disposable_viewer', function (data) {
        var data = JSON.parse(data);
        if(data['kind']=='xpi'){
            viewer=data['viewer']
                        if(viewer==false){
                            new PNotify({
                            title: "Display error",
                                text: "Can't open display, something went wrong.",
                                hide: true,
                                delay: 3000,
                                icon: 'fa fa-alert-sign',
                                opacity: 1,
                                type: 'error'
                            });
                        }else{
                            if(viewer.tlsport){
                                openTLS(viewer.host, viewer.port, viewer.tlsport, viewer.passwd, viewer.ca);
                            }else{
                                openTCP(viewer.host, viewer.port, viewer.passwd);
                            }
                        }
        }
        if(data['kind']=='html5'){
            viewer=data['viewer']
            //~ window.open('http://try.isardvdi.com:8000/?host=try.isardvdi.com&port='+viewer.port+'&passwd='+viewer.passwd); 
            window.open('http://'+viewer.host+'/?host='+viewer.host+'&port='+viewer.port+'&passwd='+viewer.passwd);            
            
        }        
        
         if(data['kind']=='file'){
            var viewerFile = new Blob([data['content']], {type: data['mime']});
            var a = document.createElement('a');
                a.download = 'console.'+data['ext'];
                a.href = window.URL.createObjectURL(viewerFile);
            var ev = document.createEvent("MouseEvents");
                ev.initMouseEvent("click", true, false, self, 0, 0, 0, 0, 0, false, false, false, false, 0, null);
                a.dispatchEvent(ev);              
                    }
    });


    socket.on('result', function (data) {
        var data = JSON.parse(data);
        new PNotify({
                title: data.title,
                text: data.text,
                hide: true,
                delay: 4000,
                icon: 'fa fa-'+data.icon,
                opacity: 1,
                type: data.type
        });
    });
    
});



function getClientViewer(data,socket){
				if(detectXpiPlugin()){
					//SPICE-XPI Plugin
                    if(isXpiBlocked()){
                            new PNotify({
                            title: "Plugin blocked",
                                text: "You should allow SpiceXPI plugin and then reload webpage.",
                                hide: true,
                                confirm: {
                                    confirm: true,
                                    cancel: false
                                },
                                //~ delay: 3000,
                                icon: 'fa fa-alert-sign',
                                opacity: 1,
                                type: 'warning'
                            });                        
                    }else{
                    socket.emit('disposable_viewer',{'pk':data['id'],'kind':'xpi'})                       
                    }
				}else{
                        new PNotify({
                            title: 'Choose display connection',
                            text: 'Open in browser (html5) or download remote-viewer file.',
                            icon: 'glyphicon glyphicon-question-sign',
                            hide: false,
                            delay: 3000,
                            confirm: {
                                confirm: true,
                                buttons: [
                                    {
                                        text: 'HTML5',
                                        addClass: 'btn-primary',
                                        click: function(notice){
                                            notice.update({
                                                title: 'You choosed html5 viewer', text: 'Viewer will be opened in new window.\n Please allow popups!', icon: true, type: 'info', hide: true,
                                                confirm: {
                                                    confirm: false
                                                },
                                                buttons: {
                                                    closer: true,
                                                    sticker: false
                                                }
                                            });                                            
                                            socket.emit('disposable_viewer',{'pk':data['id'],'kind':'html5'});
                                        }
                                    },
                                    {
                                        text: 'Download display file',
                                        click: function(notice){
                                            notice.update({
                                                title: 'You choosed to download', text: 'File will be downloaded shortly', icon: true, type: 'info', hide: true,
                                                confirm: {
                                                    confirm: false
                                                },
                                                buttons: {
                                                    closer: true,
                                                    sticker: false
                                                }
                                            });
                                            socket.emit('disposable_viewer',{'pk':data['id'],'kind':'file'});
                                        }
                                    },
                                ]
                            },
                            buttons: {
                                closer: false,
                                sticker: false
                            },
                            history: {
                                history: false
                            }
                        });                        


					}

}

