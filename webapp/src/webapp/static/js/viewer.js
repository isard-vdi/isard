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
            url:"/api/v4/item/user/vpn/config",
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
}


function setViewerButtons(desktop_id){
    $('#modalOpenViewer').data('desktop-id', desktop_id)
    $.ajax({
        type: "GET",
        url:"/api/v4/admin/item/domain/" + desktop_id + "/viewer_data",
        // async: false,
        success: function (resp) {
            // The modal may have been reopened for another desktop meanwhile
            if ($('#modalOpenViewer').data('desktop-id') !== desktop_id) return
            setViewerButtonData(desktop_id,resp)
        }
    });
}
function setViewerButtonData(desktop_id,data){
    offer=[]
    // Check if desktop has guest_ip (required for RDP viewers)
    const hasGuestIp = 'viewer' in data && 'guest_ip' in data['viewer'] && data['viewer']['guest_ip'];

    // Test the value, not key presence: a disabled viewer can be stored as null.
    var viewers = (data["guest_properties"] || {})["viewers"] || {};

    if (viewers["file_spice"]){
        offer.push({
            'text': 'SPICE',
            'type': 'spice',
            'client': 'app',
            'secure': true,
            'preferred': true
        })
    }
    if (viewers["browser_vnc"]){
        offer.push({
            'text': 'VNC browser',
            'type': 'vnc',
            'client': 'websocket',
            'secure': true,
            'preferred': false
        })
    }
    if (viewers["file_rdpgw"]){
        if (hasGuestIp) {  // Only add if IP available
            offer.push({
                'text': 'RDP',
                'type': 'rdpgw',
                'client': 'app',
                'secure': true,
                'preferred': false
            })
        }
    }
    if (viewers["file_rdpvpn"]){
        if (hasGuestIp) {  // Only add if IP available
            offer.push({
                'text': 'RDP VPN',
                'type': 'rdpvpn',
                'client': 'app',
                'secure': true,
                'preferred': false
            })
        }
    }
    if (viewers["browser_rdp"]){
        if (hasGuestIp) {  // Only add if IP available
            offer.push({
                'text': 'RDP browser',
                'type': 'rdp',
                'client': 'websocket',
                'secure': true,
                'preferred': false
            })
        }
    }

    // RDP step of the guest, shown on the RDP buttons as an icon + tooltip.
    // Admins and managers may open an unverified RDP, so nothing is disabled.
    const rdpStatus = rdpViewerStatus(data)

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
            isRdp=['rdp', 'rdpgw', 'rdpvpn'].includes(disp['type'])
            rdpIcon=(isRdp && rdpStatus) ? ' <i class="fa '+rdpStatus.icon+'"></i>' : ''
            rdpTitle=(isRdp && rdpStatus) ? ' title="'+rdpStatus.text+'" data-rdp-status="'+rdpStatus.tone+'"' : ''
            // Left-to-right readiness fill behind the label (same language as the
            // Vue frontends). Only fixed/computed values go into the HTML.
            rdpFill=(isRdp && rdpStatus && rdpStatus.progress !== undefined)
                ? '<span role="progressbar" aria-valuenow="'+rdpStatus.progress+'" aria-valuemin="0" aria-valuemax="100" aria-label="'+rdpStatus.text+'" style="position:absolute;top:0;bottom:0;left:0;z-index:0;pointer-events:none;width:'+rdpStatus.progress+'%;background-color:'+rdpStatus.fill+';"></span>'
                : ''
            btnStyle=(isRdp && rdpFill) ? 'width:'+w+'%;position:relative;overflow:hidden' : 'width:'+w+'%'
            html=br+html+prehtml+'<button data-pk="'+desktop_id+'" data-type="'+disp['type']+'" data-client="'+client+'" data-os="'+getOS()+'" type="button" class="btn '+success+' '+preferred+' btn-viewers" style="'+btnStyle+'"'+rdpTitle+'>'+rdpFill+'<span style="position:relative;z-index:1">'+lock+' '+type+' '+btntext+rdpIcon+'</span></button>'+posthtml+br
    })
    if (data.create_dict.hardware.interfaces.includes("wireguard")) {
        if('viewer' in data && 'guest_ip' in data['viewer'] && data['viewer']['guest_ip']){
            html+=prehtml+'<div id="vpn-ip-'+desktop_id+'" style="width:50% height:2000px"><i class="fa fa-lock"></i> <i class="fa fa-link"></i> Desktop IP (via VPN): '+data['viewer']['guest_ip']+'</div>'+posthtml
        }else{
            html+=prehtml+'<div id="vpn-ip-'+desktop_id+'" style="width:50% height:2000px"><i class="fa fa-lock"></i> <i class="fa fa-link"></i> Desktop IP (via VPN): <i class="fa fa-spinner fa-pulse fa-1x fa-fw"></i></div>'+posthtml
            loading='<i class="fa fa-spinner fa-pulse fa-1x fa-fw"></i>'
        }
    }
    $('#viewer-buttons').html(html);
    $('#viewer-buttons .btn-viewers').on('click', function () {
        if($('#chk-viewers').iCheck('update')[0].checked){
            preferred=true
        }else{
            preferred=false
        }
        $.ajax({
            type: "GET",
            url:"/api/v4/item/desktop/" + desktop_id + "/get-viewer/" + $(this).data('client') + "-" + $(this).data('type'),
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
                    el.setAttribute('href', data.viewer)
                    el.setAttribute('target', '_blank')
                    if (data.protocol === 'rdp') {
                        setCookie('viewerToken', getCookie('isardvdi_session'))
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

// Translucent fill colour by tone, used for the left-to-right readiness bar.
const RDP_FILL = {
    wait: 'rgba(56,189,248,0.40)',
    warn: 'rgba(251,191,36,0.45)',
    error: 'rgba(248,113,113,0.42)'
}
// How far the readiness check has advanced, so the button fills left to right.
const RDP_PROGRESS = { pending: 25, waiting: 50, verifying: 80, refused: 50, auth_failed: 80, unverified: 100 }

function rdpViewerStatus(data){
    const viewer = data.viewer || {}
    const rdp = viewer.rdp
    if (!viewer.guest_ip || !rdp) return null
    const last = viewer.rdp_last
    // Fixed texts picked by key: nothing that comes from the API is shown,
    // because the result is concatenated into the button HTML.
    const texts = {
        pending: 'Waiting for the desktop RDP service',
        waiting: 'Waiting for the desktop RDP service',
        verifying: 'Verifying the RDP credentials',
        refused: 'The desktop refuses RDP',
        auth_failed: 'The stored RDP credentials are not valid in the desktop',
        unverified: 'RDP available, credentials not verified'
    }
    if (rdp.state === 'ready' && last && !last.connected) {
        return { tone: 'error', icon: 'fa-exclamation-triangle', progress: 100, fill: RDP_FILL.error, text: last.result === 'auth_failed' ? texts.auth_failed : 'The last RDP connection failed' }
    }
    if (rdp.state === 'ready' || !Object.prototype.hasOwnProperty.call(texts, rdp.state)) return null
    // Admins also get the internal code, only when it is one of the plain
    // words the vpn writes, so it is safe inside the HTML attribute.
    const code = (typeof rdp.reason === 'string' && /^[a-z0-9_]{1,40}$/.test(rdp.reason)) ? ' [' + rdp.reason + ']' : ''
    const progress = RDP_PROGRESS[rdp.state]
    if (['refused', 'auth_failed'].includes(rdp.state)) return { tone: 'error', icon: 'fa-exclamation-triangle', progress: progress, fill: RDP_FILL.error, text: texts[rdp.state] + code }
    // A probe that could not verify (no NLA, no credentials, or a failed check)
    // does not block: the admin may connect, with a warning.
    if (rdp.state === 'unverified') return { tone: 'warn', icon: 'fa-exclamation-triangle', progress: progress, fill: RDP_FILL.warn, text: texts.unverified }
    return { tone: 'wait', icon: 'fa-spinner fa-pulse', progress: progress, fill: RDP_FILL.wait, text: texts[rdp.state] }
}

function viewerButtonsIP(id,ip){
    if (!$('#modalOpenViewer').hasClass('in') || $('#modalOpenViewer').data('desktop-id') !== id) return
    // Re-fetch viewer data and re-render buttons now that IP is available
    setViewerButtons(id);
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
    var gp = data.guest_properties || {};
    var viewers = gp.viewers || {};
    if(gp.fullscreen){
        $(div+' #guest_properties-fullscreen').iCheck('check');
    }else{
        $(div+' #guest_properties-fullscreen').iCheck('uncheck');
    }
    if(viewers.file_spice){
        $(div+' #viewers-file_spice').iCheck('check');
    }else{
        $(div+' #viewers-file_spice').iCheck('uncheck');
    }
    if(viewers.file_rdpgw){
        $(div+' #viewers-file_rdpgw').iCheck('check');
    }else{
        $(div+' #viewers-file_rdpgw').iCheck('uncheck');
    }
    if(viewers.file_rdpvpn){
        $(div+' #viewers-file_rdpvpn').iCheck('check');
    }else{
        $(div+' #viewers-file_rdpvpn').iCheck('uncheck');
    }
    if(viewers.browser_vnc){
        $(div+' #viewers-browser_vnc').iCheck('check');
    }else{
        $(div+' #viewers-browser_vnc').iCheck('uncheck');
    }
    if(viewers.browser_rdp){
        $(div+' #viewers-browser_rdp').iCheck('check');
    }else{
        $(div+' #viewers-browser_rdp').iCheck('uncheck');
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
