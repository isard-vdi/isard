/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

$(document).ready(function() {
            $('#disposable').on('change', function() {
                console.log(this.value)
                if(this.value!="default"){
                    socket.emit('disposables_add',{'pk':this.value}) 
                    $('#disposable').prop("disabled",true);
                    $('#disposable option[value="default"]').text(' Wait till '+$("#disposable option[value='"+this.value+"']").text()+' viewer opens...');
                    $('#disposable option[value="default"]').prop("selected",true);
                }
            })  


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
        console.log(data)
        console.log('new_data: (this will open viewer, everything seems ok!)')
        
        
        $('#disposable option[value="default"]').text('Choose a desktop...');
        $('#disposable option[value="default"]').prop("selected",true);
        $('#disposable').prop("disabled",false);
        

                                                //~ var url = '/desktops/download_viewer/'+getOS()+'/'+data['id'];
                                                //~ var anchor = document.createElement('a');
                                                    //~ anchor.setAttribute('href', url);
                                                    //~ anchor.setAttribute('download', 'console.vv');
                                                //~ var ev = document.createEvent("MouseEvents");
                                                    //~ ev.initMouseEvent("click", true, false, self, 0, 0, 0, 0, 0, false, false, false, false, 0, null);
                                                    //~ anchor.dispatchEvent(ev);    
                                                    
                                                    
        
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
