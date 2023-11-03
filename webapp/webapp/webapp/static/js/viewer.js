/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/


function startClientVpnSocket(socket){
    $('#btn-uservpnconfig').on('click', function () {
        $.ajax({
            type: "GET",
            url:"/api/v3/user/vpn/config",
            success: function (data) {
                const el = document.createElement('a')
                const content = data.content
                el.setAttribute(
                    'href',
                    `data:${data.mime};charset=utf-8,${encodeURIComponent(content)}`
                )
                el.setAttribute('download', `${data.name}.${data.ext}`)
                el.style.display = 'none'
                document.body.appendChild(el)
                el.click()
                document.body.removeChild(el)
            }
        })
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


function setViewerButtons(desktop_id){
    $.ajax({
        type: "GET",
        url:"/api/v3/admin/domain/" + desktop_id + "/viewer_data",
        // async: false,
        success: function (resp) {
            setViewerButtonData(desktop_id,resp)
        }
    });
}
function setViewerButtonData(desktop_id,data){
    offer=[]
    if ("file_spice" in data["guest_properties"]["viewers"]){
        offer.push({
            'text': 'SPICE',
            'type': 'spice',
            'client': 'app',
            'secure': true,
            'preferred': true
        })
    }
    if ("browser_vnc" in data["guest_properties"]["viewers"]){
        offer.push({
            'text': 'VNC browser',
            'type': 'vnc',
            'client': 'websocket',
            'secure': true,
            'preferred': false
        })
    }
    if ("file_rdpgw" in data["guest_properties"]["viewers"]){
        offer.push({
            'text': 'RDP',
            'type': 'rdpgw',
            'client': 'app',
            'secure': true,
            'preferred': false
        })
    }
    if ("file_rdpvpn" in data["guest_properties"]["viewers"]){
        offer.push({
            'text': 'RDP VPN',
            'type': 'rdpvpn',
            'client': 'app',
            'secure': true,
            'preferred': false
        })
    }
    if ("browser_rdp" in data["guest_properties"]["viewers"]){
        offer.push({
            'text': 'RDP browser',
            'type': 'rdp',
            'client': 'websocket',
            'secure': true,
            'preferred': false
        })
    }

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
            if(disp['preferred']){
                success='btn-success'
                preferred='btn-lg'
                w='70'
                br='<br>'
            }
            if(disp['secure']){
                lock='<i class="fa fa-lock"></i>'
            }
            type=['rdp', 'vnc'].includes(disp['type'])? '<i class="fa fa-html5"></i>' : '<i class="fa fa-download"></i>'
            btntext=disp['text']
            client=['rdp', 'vnc'].includes(disp['type'])? 'browser' : 'file'
            html=br+html+prehtml+'<button data-pk="'+desktop_id+'" data-type="'+disp['type']+'" data-client="'+client+'" data-os="'+getOS()+'" type="button" class="btn '+success+' '+preferred+' btn-viewers" style="width:'+w+'%">'+lock+' '+type+' '+btntext+'</button>'+posthtml+br
    })
    if (data.create_dict.hardware.interfaces.includes("wireguard")) {
        if('viewer' in data && 'guest_ip' in data['viewer']){
            html+=prehtml+'<div id="vpn-ip-'+desktop_id+'" style="width:50% height:2000px"><i class="fa fa-lock"></i> <i class="fa fa-link"></i> Desktop IP (via VPN): '+data['viewer']['guest_ip']+'</div>'+posthtml
        }else{
            html+=prehtml+'<div id="vpn-ip-'+desktop_id+'" style="width:50% height:2000px"><i class="fa fa-lock"></i> <i class="fa fa-link"></i> Desktop IP (via VPN): <i class="fa fa-spinner fa-pulse fa-1x fa-fw"></i></div>'+posthtml
            loading='<i class="fa fa-spinner fa-pulse fa-1x fa-fw"></i>'
        }
    }
    $('#viewer-buttons').html(html);
    if (data.create_dict.hardware.interfaces.includes("wireguard")) {
        if(!('viewer' in data && 'guest_ip' in data['viewer'])){
            $('#viewer-buttons button[data-type^="rdp"]').prop("disabled", true).append(loading);
        }
    }
    $('#viewer-buttons .btn-viewers').on('click', function () {
        if($('#chk-viewers').iCheck('update')[0].checked){
            preferred=true
        }else{
            preferred=false
        }
        $.ajax({
            type: "GET",
            url:"/api/v3/desktop/" + desktop_id + "/viewer/" + $(this).data('client') + "-" + $(this).data('type'),
            success: function (data) {
                var el = document.createElement('a')
                if (data.kind === 'file') {
                    el.setAttribute(
                        'href',
                        `data:${data.mime};charset=utf-8,${encodeURIComponent(data.content)}`
                    )
                    el.setAttribute('download', `${data.name}.${data.ext}`)
                } else if (data.kind === 'browser') {
                    setCookie('browser_viewer', data.cookie)
                    setCookie('token', localStorage.token)
                    el.setAttribute('href', data.viewer)
                    el.setAttribute('target', '_blank')
                    if (data.protocol === 'rdp') {
                        localStorage.viewerToken = localStorage.token
                    }
                }
                el.style.display = 'none'
                document.body.appendChild(el)
                el.click()
                document.body.removeChild(el)
            }
        })
        $("#modalOpenViewer").modal('hide');
    });
}

function viewerButtonsIP(id,ip){
    $('#vpn-ip-'+id).html('<i class="fa fa-lock"></i> <i class="fa fa-link"></i> Desktop IP (via vpn): '+ip)
    $('#vpn-ip-'+id+' i.fa-spinner').remove()
    $('#viewer-buttons button[data-type^="rdp"]').prop("disabled", false)
    $('#viewer-buttons button[data-type^="rdp"] i.fa-spinner').remove()
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

function setViewers(div,data){
    if(data.guest_properties.fullscreen){
        $(div+' #guest_properties-fullscreen').iCheck('check');
    }else{
        $(div+' #guest_properties-fullscreen').iCheck('update')[0].unchecked;
    }
    if("file_spice" in data.guest_properties.viewers){
        $(div+' #viewers-file_spice').iCheck('check');
    }else{
        $(div+' #viewers-file_spice').iCheck('update')[0].unchecked;
    }
    if("file_rdpgw" in data.guest_properties.viewers){
        $(div+' #viewers-file_rdpgw').iCheck('check');
    }else{
        $(div+' #viewers-file_rdpgw').iCheck('update')[0].unchecked;
    }
    if("file_rdpvpn" in data.guest_properties.viewers){
        $(div+' #viewers-file_rdpvpn').iCheck('check');
    }else{
        $(div+' #viewers-file_rdpvpn').iCheck('update')[0].unchecked;
    }
    if("browser_vnc" in data.guest_properties.viewers){
        $(div+' #viewers-browser_vnc').iCheck('check');
    }else{
        $(div+' #viewers-browser_vnc').iCheck('update')[0].unchecked;
    }
    if("browser_rdp" in data.guest_properties.viewers){
        $(div+' #viewers-browser_rdp').iCheck('check');
    }else{
        $(div+' #viewers-browser_rdp').iCheck('update')[0].unchecked;
    }
}

function parseViewersOptions(data){
    if(data['guest_properties-fullscreen']){
        data["guest_properties-fullscreen"]=true
    }else{
        data["guest_properties-fullscreen"]=false
    }

    if(data['viewers-file_spice']){
        delete data["viewers-file_spice"]
        data["guest_properties-viewers-file_spice-options"]=null
    }
    if(data['viewers-browser_vnc']){
        delete data["viewers-browser_vnc"]
        data["guest_properties-viewers-browser_vnc-options"]=null
    }
    if(data['viewers-browser_rdp']){
        delete data["viewers-browser_rdp"]
        data["guest_properties-viewers-browser_rdp-options"]=null
    }
    if(data['viewers-file_rdpgw']){
        delete data["viewers-file_rdpgw"]
        data["guest_properties-viewers-file_rdpgw-options"]=null
    }
    if(data['viewers-file_rdpvpn']){
        delete data["viewers-file_rdpvpn"]
        data["guest_properties-viewers-file_rdpvpn-options"]=null
    }
    delete data["options"]
    return data
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
