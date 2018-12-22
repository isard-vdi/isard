      var useragent = navigator.userAgent;
      patt = new RegExp("Firefox");
      res = patt.test(useragent);
      if (res) {
        var seconds = new Date().getTime() / 1000;
        var url = new URL(window.location);
        var opened = window.open("https://" + document.domain + ":"+url.searchParams.get("port")+"?t=" + seconds,"");
        alert("Please allow the pop-up window.\nIt is used to accept the certificate, if required.\nThis is due to a Firefox bug.");
      }
