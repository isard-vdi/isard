/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

function startClientViewerSocket(socket){
    socket.on('domain_viewer', function (data) {
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


}    
    

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
                    socket.emit('domain_viewer',{'pk':data['id'],'kind':'xpi'})                       
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
                                            socket.emit('domain_viewer',{'pk':data['id'],'kind':'html5'});
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
                                            socket.emit('domain_viewer',{'pk':data['id'],'kind':'file'});
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






	function detectXpiPlugin(){
		var pluginsFound = false;
		if (navigator.plugins && navigator.plugins.length > 0) {
			var daPlugins = [ "Spice" ];
			var pluginsAmount = navigator.plugins.length;
			for (counter = 0; counter < pluginsAmount; counter++) {
				var numFound = 0;
				for (namesCounter = 0; namesCounter < daPlugins.length; namesCounter++) {
					if ((navigator.plugins[counter].name.indexOf(daPlugins[namesCounter]) > 0)
						|| (navigator.plugins[counter].description.indexOf(daPlugins[namesCounter]) >= 0)) {
						numFound++;
					}
				}
				if (numFound == daPlugins.length) {
				pluginsFound = true;
				break;
				}
			}

		}
		return pluginsFound;
	}

    function isXpiBlocked(){
        var embed = document.embeds[0];
        if (typeof embed.connect === "function") { 
            return false;
        }
        return true;
    }
    
	function openTCP(spice_host,spice_port,spice_passwd)
	{
		var embed = document.embeds[0];
		embed.hostIP = spice_host;
		embed.port = spice_port;
		embed.Password = spice_passwd;
		embed.fullScreen = true;
		embed.fAudio = true;
		embed.UsbListenPort = 1;
		embed.UsbAutoShare = 1;
		embed.connect();
	}

	function openTLS(spice_host,spice_port,spice_tls,spice_passwd,ca)
	{		
		var embed = document.embeds[0];
		embed.hostIP = spice_host;
		//~ embed.port = spice_port;
		embed.SecurePort = spice_tls;
		embed.Password = spice_passwd;
		embed.CipherSuite = "";
		embed.SSLChannels = "";
		embed.HostSubject = "";
		embed.fullScreen = true;
		embed.AdminConsole = "";
		embed.Title = "";
		embed.dynamicMenu = "";
		embed.NumberOfMonitors = "";
		embed.GuestHostName = "";
		embed.HotKey = "";
		embed.NoTaskMgrExecution = "";
		embed.SendCtrlAltDelete = "";
		embed.UsbListenPort = "";
		embed.UsbAutoShare = true;
		embed.Smartcard = "";
		embed.ColorDepth = "";
		embed.DisableEffects = "";
		embed.TrustStore = ca;
		embed.Proxy = "";
		embed.connect();
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
