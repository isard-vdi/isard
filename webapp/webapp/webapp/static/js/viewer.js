/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

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
/*              {
             'type': 'spice',
             'client': 'websocket',
             'secure': true,
             'preferred': false
             }, */
             {
                'type': 'vpn', 
                'client': 'app',
                'secure': true,
                'preferred': false
            },             
             //~ {
             //~ 'type': 'vnc', 
             //~ 'client': 'websocket', 
             //~ 'secure': true,
             //~ 'preferred': false
             //~ },
             //~ {
             //~ 'type': 'vnc', 
             //~ 'client': 'app', 
             //~ 'secure': false,
             //~ 'preferred': false
             //~ },             
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
            html=br+prehtml+html+'<button data-pk="'+id+'" data-type="'+disp['type']+'" data-client="'+client+'" data-os="'+getOS()+'" type="button" class="btn '+success+' '+preferred+' btn-viewers" style="width:'+w+'%">'+lock+' '+type+' '+btntext+'</button>'+posthtml+br;
    })
    $('#viewer-buttons').html(html);
    $('#viewer-buttons .btn-viewers').on('click', function () {
        if($('#chk-viewers').iCheck('update')[0].checked){
            preferred=true
        }else{
            preferred=false
        }
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
    
//~ function getClientViewer(data,socket){
                //~ if(detectXpiPlugin()){
                    //~ //SPICE-XPI Plugin
                    //~ if(isXpiBlocked()){
                            //~ new PNotify({
                            //~ title: "Plugin blocked",
                                //~ text: "You should allow SpiceXPI plugin and then reload webpage.",
                                //~ hide: true,
                                //~ confirm: {
                                    //~ confirm: true,
                                    //~ cancel: false
                                //~ },
                                //~ // delay: 3000,
                                //~ icon: 'fa fa-alert-sign',
                                //~ opacity: 1,
                                //~ type: 'warning'
                            //~ });                        
                    //~ }else{
                    //~ socket.emit('domain_viewer',{'pk':data['id'],'kind':'xpi'})                       
                    //~ }
                //~ }else{
                        //~ new PNotify({
                            //~ title: 'Choose display connection',
                            //~ text: 'Open in browser (html5) or download remote-viewer file.',
                            //~ icon: 'glyphicon glyphicon-question-sign',
                            //~ hide: false,
                            //~ delay: 3000,
                            //~ confirm: {
                                //~ confirm: true,
                                //~ buttons: [
                                    //~ {
                                        //~ text: 'HTML5',
                                        //~ addClass: 'btn-primary',
                                        //~ click: function(notice){
                                            //~ notice.update({
                                                //~ title: 'You choosed html5 viewer', text: 'Viewer will be opened in new window.\n Please allow popups!', icon: true, type: 'info', hide: true,
                                                //~ confirm: {
                                                    //~ confirm: false
                                                //~ },
                                                //~ buttons: {
                                                    //~ closer: true,
                                                    //~ sticker: false
                                                //~ }
                                            //~ });                                            
                                            //~ socket.emit('domain_viewer',{'pk':data['id'],'kind':'html5'});
                                        //~ }
                                    //~ },
                                    //~ {
                                        //~ text: 'Download display file',
                                        //~ click: function(notice){
                                            //~ notice.update({
                                                //~ title: 'You choosed to download', text: 'File will be downloaded shortly', icon: true, type: 'info', hide: true,
                                                //~ confirm: {
                                                    //~ confirm: false
                                                //~ },
                                                //~ buttons: {
                                                    //~ closer: true,
                                                    //~ sticker: false
                                                //~ }
                                            //~ });
                                            //~ socket.emit('domain_viewer',{'pk':data['id'],'kind':'file'});
                                        //~ }
                                    //~ },
                                //~ ]
                            //~ },
                            //~ buttons: {
                                //~ closer: false,
                                //~ sticker: false
                            //~ },
                            //~ history: {
                                //~ history: false
                            //~ }
                        //~ });                        


                    //~ }

//~ }



    //~ function detectXpiPlugin(){
        //~ var pluginsFound = false;
        //~ if (navigator.plugins && navigator.plugins.length > 0) {
            //~ var daPlugins = [ "Spice" ];
            //~ var pluginsAmount = navigator.plugins.length;
            //~ for (counter = 0; counter < pluginsAmount; counter++) {
                //~ var numFound = 0;
                //~ for (namesCounter = 0; namesCounter < daPlugins.length; namesCounter++) {
                    //~ if ((navigator.plugins[counter].name.indexOf(daPlugins[namesCounter]) > 0)
                        //~ || (navigator.plugins[counter].description.indexOf(daPlugins[namesCounter]) >= 0)) {
                        //~ numFound++;
                    //~ }
                //~ }
                //~ if (numFound == daPlugins.length) {
                //~ pluginsFound = true;
                //~ break;
                //~ }
            //~ }

        //~ }
        //~ return pluginsFound;
    //~ }

    //~ function isXpiBlocked(){
        //~ var embed = document.embeds[0];
        //~ if (typeof embed.connect === "function") { 
            //~ return false;
        //~ }
        //~ return true;
    //~ }                # ~ if viewer['port']:
                    //////# ~ viewer['port'] = viewer['port'] if viewer['port'] else viewer['tlsport']
                    ////# ~ viewer['port'] = "5"+ viewer['port']
    
    //~ function openTCP(spice_host,spice_port,spice_passwd)
    //~ {
        //~ var embed = document.embeds[0];
        //~ embed.hostIP = spice_host;
        //~ embed.port = spice_port;
        //~ embed.Password = spice_passwd;
        //~ embed.fullScreen = true;
        //~ embed.fAudio = true;
        //~ embed.UsbListenPort = 1;
        //~ embed.UsbAutoShare = 1;
        //~ embed.connect();
    //~ }

    //~ function openTLS(spice_host,spice_port,spice_tls,spice_passwd,ca)
    //~ {       
        //~ var embed = document.embeds[0];
        //~ embed.hostIP = spice_host;
        // embed.port = spice_port;
        //~ embed.SecurePort = spice_tls;
        //~ embed.Password = spice_passwd;
        //~ embed.CipherSuite = "";
        //~ embed.SSLChannels = "";
        //~ embed.HostSubject = "";
        //~ embed.fullScreen = true;
        //~ embed.AdminConsole = "";
        //~ embed.Title = "";
        //~ embed.dynamicMenu = "";
        //~ embed.NumberOfMonitors = "";
        //~ embed.GuestHostName = "";
        //~ embed.HotKey = "";
        //~ embed.NoTaskMgrExecution = "";
        //~ embed.SendCtrlAltDelete = "";
        //~ embed.UsbListenPort = "";
        //~ embed.UsbAutoShare = true;
        //~ embed.Smartcard = "";
        //~ embed.ColorDepth = "";
        //~ embed.DisableEffects = "";
        //~ embed.TrustStore = ca;
        //~ embed.Proxy = "";
        //~ embed.connect();
    //~ }
  
//~ function chooseViewer(data,socket){
    //~ os=getOS()
    //~ new PNotify({
        //~ title: 'Choose display connection',
        //~ text: 'Open in browser (html5) or download remote-viewer file.',
        //~ icon: 'glyphicon glyphicon-question-sign',
        //~ hide: false,
        //~ delay: 3000,
        //~ confirm: {
            //~ confirm: true,
            //~ buttons: [
                //~ {
                    //~ text: 'SPICE BROWSER',
                    //~ addClass: 'btn-primary',
                    //~ click: function(notice){
                        //~ notice.update({
                            //~ title: 'You choosed spice browser viewer', text: 'Viewer will be opened in new window.\n Please allow popups!', icon: true, type: 'info', hide: true,
                            //~ confirm: {
                                //~ confirm: false
                            //~ },
                            //~ buttons: {
                                //~ closer: true,
                                //~ sticker: false
                            //~ }
                        //~ });                                            
                        //~ socket.emit('domain_viewer',{'pk':data['id'],'kind':'spice-html5','os':os});
                    //~ }
                //~ },
                //~ {
                    //~ text: 'SPICE CLIENT',
                    //~ addClass: 'btn-primary',
                    //~ click: function(notice){
                        //~ notice.update({
                            //~ title: 'You choosed spice client viewer', text: 'File will be downloaded. Open it with spice remote-viewer.', icon: true, type: 'info', hide: true,
                            //~ confirm: {
                                //~ confirm: false
                            //~ },
                            //~ buttons: {
                                //~ closer: true,
                                //~ sticker: false
                            //~ }
                        //~ });                                            
                        //~ socket.emit('domain_viewer',{'pk':data['id'],'kind':'spice-client','os':os});
                    //~ }
                //~ },              
                //~ {
                    //~ text: 'VNC BROWSER',
                    //~ addClass: 'btn-primary',
                    //~ click: function(notice){
                        //~ notice.update({
                            //~ title: 'You choosed VNC browser viewer', text: 'Viewer will be opened in new window.\n Please allow popups!', icon: true, type: 'info', hide: true,
                            //~ confirm: {
                                //~ confirm: false
                            //~ },
                            //~ buttons: {
                                //~ closer: true,
                                //~ sticker: false
                            //~ }
                        //~ });                                            
                        //~ socket.emit('domain_viewer',{'pk':data['id'],'kind':'vnc-html5','os':os});
                    //~ }
                //~ },
                //~ {
                    //~ text: 'VNC CLIENT',
                    //~ addClass: 'btn-primary',
                    //~ click: function(notice){
                        //~ notice.update({
                            //~ title: 'You choosed VNC client viewer', text: 'File will be downloaded. Open it with VNC client app.', icon: true, type: 'info', hide: true,
                            //~ confirm: {
                                //~ confirm: false
                            //~ },
                            //~ buttons: {
                                //~ closer: true,
                                //~ sticker: false
                            //~ }
                        //~ });                                            
                        //~ socket.emit('domain_viewer',{'pk':data['id'],'kind':'vnc-client','os':os});
                    //~ }
                //~ },  
            //~ ]
        //~ },
        //~ buttons: {
            //~ closer: false,
            //~ sticker: false
        //~ },
        //~ history: {
            //~ history: false
        //~ }
    //~ });                        
//~ }
