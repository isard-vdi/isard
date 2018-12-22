/*
* Copyright 2017 the Isard-vdi project authors:
*      Josep Maria Viñolas Auquer
*      Alberto Larraz Dalmases
* License: AGPLv3
*/

//~ $(document).ready(function() {
	//~ function KeyPress(e) {
		  //~ var evtobj = window.event? event : e;
		  //~ if (evtobj.keyCode == 123 && evtobj.ctrlKey){
			  //~ var notice = new PNotify({
						//~ text: $('#form_notice').html(),
						//~ icon: false,
						//~ width: 'auto',
						//~ hide: false,
						//~ buttons: {
							//~ closer: false,
							//~ sticker: false
						//~ },
						//~ insert_brs: false
					//~ });
					
					//~ notice.get().find('form.pf-form').on('click', '[name=cancel]', function() {
						//~ notice.remove();
					//~ }).submit(function() {
						//~ var username = $(this).find('input[name=username]').val();
						//~ var password = $(this).find('input[name=password]').val();
						//~ if (!username) {
							//~ alert('Please provide a username.');
							//~ return false;
						//~ }
						
						//~ api.ajax('/about','POST',{'username':username,'password':password}).done(function() {
							//~ notice.update({
								//~ title: 'Welcome',
								//~ text: 'Successfully logged in as ' + username,
								//~ icon: true,
								//~ width: PNotify.prototype.options.width,
								//~ hide: true,
								//~ buttons: {
									//~ closer: true,
									//~ sticker: true
								//~ },
								//~ type: 'success'
							//~ });
							//~ window.location.replace('/about');
						//~ });
						//~ return false;
					//~ });
			  
		  //~ }
	//~ }

	//~ document.onkeydown = KeyPress;
//~ });
