/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

function startClientVpnSocket(socket){
    $('#btn-uservpninstall').on('click', function () {
        socket.emit('vpn',{'vpn':'users','kind':'install','os':getOS()});   
    });
    $('#btn-uservpnconfig').on('click', function () {
        socket.emit('vpn',{'vpn':'users','kind':'config','os':getOS()});   
    });
    $('#btn-uservpnclient').on('click', function () {
        socket.emit('vpn',{'vpn':'users','kind':'client','os':getOS()});   
    });

    socket.on('vpn', function (data) {
        var data = JSON.parse(data);
        if(data['kind']=='url'){
            window.open(data['url'], '_blank');            
        }
        if(data['kind']=='file'){
            var vpnFile = new Blob([data['content']], {type: data['mime']});
            var a = document.createElement('a');
                a.download = data['name']+'.'+data['ext'];
                a.href = window.URL.createObjectURL(vpnFile);
            var ev = document.createEvent("MouseEvents");
                ev.initMouseEvent("click", true, false, self, 0, 0, 0, 0, 0, false, false, false, false, 0, null);
                a.dispatchEvent(ev);              
        }
    });
}

function setViewerButtons(id,socket,offer){
    offer=[
             {
             'type': 'spice', 
             'client': 'app',
             'secure': true,
             'preferred': true
             },
             {
             'type': 'vnc', 
             'client': 'websocket',
             'secure': true,
             'preferred': false
             },
             {
                'type': 'rdp', 
                'client': 'app',
                'secure': true,
                'preferred': false
            }
            ]
    html=""
    $.each(offer, function(idx,disp){
            prehtml='<div class="row"><div class="col-12 text-center">'
            posthtml='</div></div>'
            success='btn-round btn-info'
            preferred=''
            w='50'
            lock='<i class="fa fa-unlock"></i>'
            type=''
            btntext=''
            br=''
            if(disp['preferred']){success='btn-success';preferred='btn-lg';w='70';br='<br>'}
            if(disp['secure']){lock='<i class="fa fa-lock"></i>';}
            if(disp['client']=='app')
                {type='<i class="fa fa-download"></i>';btntext=disp['type'].toUpperCase()+' Application';client='client';}
            else if(disp['client']=='websocket')
                {type='<i class="fa fa-html5"></i>';btntext=disp['type'].toUpperCase()+' Browser';client='html5'}
            if(disp['type'] == 'rdp'){ 
                html=br+prehtml+html+'<button data-pk="'+id+'" data-type="'+disp['type']+'" data-client="'+client+'" data-os="'+getOS()+'" type="button" class="btn '+success+' '+preferred+' btn-viewers" style="width:'+w+'%">'+lock+' '+type+' '+btntext+'</button>'+posthtml+br;   
                typevpn='<i class="fa network-wired"></i>';btntextvpn='Desktop IP: ';client='client';
                //html=br+prehtml+html+'<button data-pk="'+id+'" data-type="vpn" data-client="'+client+'" data-os="'+getOS()+'" type="button" class="btn btn-light '+preferred+' btn-viewers" style="width:'+w+'%">'+lock+' '+typevpn+' '+btntextvpn+'</button>'+posthtml+br;
                html=br+prehtml+html+'<div data-pk="'+id+'" data-type="vpn" data-client="'+client+'" data-os="'+getOS()+' style="width:'+w+'% height:2000px">'+lock+' '+typevpn+' '+btntextvpn+'</button>'+posthtml+br;
                //html=br+prehtml+html+'<button btn-viewers" style="width:'+w+'%">'+lock+' '+type+' '+btntext+'</button>'+posthtml+br;
            }else{
                //type='<i class="fa fa-download"></i>';btntext=disp['type'].toUpperCase()+' Application';client='client'; 
                html=br+prehtml+html+'<button data-pk="'+id+'" data-type="'+disp['type']+'" data-client="'+client+'" data-os="'+getOS()+'" type="button" class="btn '+success+' '+preferred+' btn-viewers" style="width:'+w+'%">'+lock+' '+type+' '+btntext+'</button>'+posthtml+br;
            }
    })
    $('#viewer-buttons').html(html);
    loading='<i class="fa fa-spinner fa-pulse fa-1x fa-fw"></i>'
    //$('#viewer-buttons button[data-type="vpn"]').html(loading)
    $('#viewer-buttons button[data-type="rdp"]').prop("disabled",true).html($('#viewer-buttons button[data-type="rdp"]').html()+loading);
    $('#viewer-buttons div[data-type="vpn"]').prop("disabled",true).html($('#viewer-buttons div[data-type="vpn"]').html()+loading);
    $('#viewer-buttons .btn-viewers').on('click', function () {
        if($('#chk-viewers').iCheck('update')[0].checked){
            preferred=true
        }else{
            preferred=false
        }
        console.log($(this).data('type')+'-'+$(this).data('client'))
        socket.emit('domain_viewer',{'pk':id,'kind':$(this).data('type')+'-'+$(this).data('client'),'os':$(this).data('os'),'preferred':preferred});
        $("#modalOpenViewer").modal('hide');        
    });
}



function setCookie(name,value,days) {
    var expires = "";
    if (days) {
        var date = new Date();
        date.setTime(date.getTime() + (days*24*60*60*1000));
        expires = "; expires=" + date.toUTCString();
    }
    document.cookie = name + "=" + (value || "")  + expires + "; path=/";
}

function startClientViewerSocket(socket){
    socket.on('domain_viewer', function (data) {
        var data = JSON.parse(data);
        if(data['kind']=='url'){
            setCookie('isard', data['cookie'], 1)
            window.open(data['viewer'], '_blank');            
        }
        if(data['kind']=='file'){
            var viewerFile = new Blob([data['content']], {type: data['mime']});
            var a = document.createElement('a');
                if(data['ext']=='conf'){name='isard-vpn'}else{name='console'}
                a.download = name+'.'+data['ext'];
                a.href = window.URL.createObjectURL(viewerFile);
            var ev = document.createEvent("MouseEvents");
                ev.initMouseEvent("click", true, false, self, 0, 0, 0, 0, 0, false, false, false, false, 0, null);
                a.dispatchEvent(ev);              
        }
    });
}   


function setViewerHelp(){
    $(".howto-"+getOS()).css("display", "block");
}    

function getOS() {
      var userAgent = window.navigator.userAgent,
          platform = window.navigator.platform,
          macosPlatforms = ['Macintosh', 'MacIntel', 'MacPPC', 'Mac68K'],
          windowsPlatforms = ['Win32', 'Win64', 'Windows', 'WinCE'],
          iosPlatforms = ['iPhone', 'iPad', 'iPod'],
          os = null;
      if (macosPlatforms.indexOf(platform) !== -1) {
        os = 'MacOS';
      } else if (iosPlatforms.indexOf(platform) !== -1) {
        os = 'iOS';
      } else if (windowsPlatforms.indexOf(platform) !== -1) {
        os = 'Windows';
      } else if (/Android/.test(userAgent)) {
        os = 'Android';
      } else if (!os && /Linux/.test(platform)) {
        os = 'Linux';
      }
      return os;
}
