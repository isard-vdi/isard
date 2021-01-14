<template>
            <div class="flexgrid">
                <div class="logo">
                    <img src="../../assets/isard.png" style="width: 100px"><p style="fontSize: 2rem;"><b>IsardVDI</b></p>
                </div>
                <div class="box">
                    <slot />
                </div> 
                <div class="alt-logins"> 
                    <p><button type="button" class="login-with-google-btn" >Sign in with Google</button></p>
                    <p style="fontSize: 2rem; margin-left: 0.5em; padding-bottom: 0.5em"><button class="btn-auth btn-github">Sign in with <b>GitHub</b></button></p>
                </div>       
                <div class="copyright"> 
                    <div>
                        <i class="pi pi-desktop" style="fontSize: 2rem; margin-right: 0.5em"></i>Isard VDI
                    </div>
                    <br/>
                    <div>
                        2021 All Rights Reserved. AGPLv3
                    </div>
                </div>  
            </div>
</template>

<style lang="scss">
   

	.flexgrid {
        display: flex;
        justify-content: center;
        align-items: center;
        height: 100vh;
        padding: 40px;
        margin: 0;
        background: #222222;
        background: #16222A; /* fallback for old browsers */
        background: -webkit-linear-gradient(to top, #1e303b , #3A6073); /* Chrome 10-25, Safari 5.1-6 */
        background: linear-gradient(to top, #294457 , #3c85aa); /* W3C, IE 10+/ Edge, Firefox 16+, Chrome 26+, Opera 12+, Safari 7+ */
        flex-direction: column;

         .logo {
        margin-top: 10px;
        color: white;
        }


		.box {
			text-align: center;
            margin-top: 5em;
		}

        .alt-logins {
            display: flex;
            color: white;
			text-align: center;
			padding: 1rem;
            flex-direction: row;
            justify-content: center;
            align-items: center;
		}

        .copyright {
            color: white;
			text-align: center;
			padding: 1rem;
            margin-top: auto;
		}
	}

    .login-with-google-btn {
  transition: background-color .3s, box-shadow .3s;
    
  padding: 12px 16px 12px 42px;
  border: none;
  border-radius: 3px;
  box-shadow: 0 -1px 0 rgba(0, 0, 0, .04), 0 1px 1px rgba(0, 0, 0, .25);
  
  color: #757575;
  font-size: 14px;
  font-weight: 500;
  font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Oxygen,Ubuntu,Cantarell,"Fira Sans","Droid Sans","Helvetica Neue",sans-serif;
  
  background-image: url(data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMTgiIGhlaWdodD0iMTgiIHhtbG5zPSJodHRwOi8vd3d3LnczLm9yZy8yMDAwL3N2ZyI+PGcgZmlsbD0ibm9uZSIgZmlsbC1ydWxlPSJldmVub2RkIj48cGF0aCBkPSJNMTcuNiA5LjJsLS4xLTEuOEg5djMuNGg0LjhDMTMuNiAxMiAxMyAxMyAxMiAxMy42djIuMmgzYTguOCA4LjggMCAwIDAgMi42LTYuNnoiIGZpbGw9IiM0Mjg1RjQiIGZpbGwtcnVsZT0ibm9uemVybyIvPjxwYXRoIGQ9Ik05IDE4YzIuNCAwIDQuNS0uOCA2LTIuMmwtMy0yLjJhNS40IDUuNCAwIDAgMS04LTIuOUgxVjEzYTkgOSAwIDAgMCA4IDV6IiBmaWxsPSIjMzRBODUzIiBmaWxsLXJ1bGU9Im5vbnplcm8iLz48cGF0aCBkPSJNNCAxMC43YTUuNCA1LjQgMCAwIDEgMC0zLjRWNUgxYTkgOSAwIDAgMCAwIDhsMy0yLjN6IiBmaWxsPSIjRkJCQzA1IiBmaWxsLXJ1bGU9Im5vbnplcm8iLz48cGF0aCBkPSJNOSAzLjZjMS4zIDAgMi41LjQgMy40IDEuM0wxNSAyLjNBOSA5IDAgMCAwIDEgNWwzIDIuNGE1LjQgNS40IDAgMCAxIDUtMy43eiIgZmlsbD0iI0VBNDMzNSIgZmlsbC1ydWxlPSJub256ZXJvIi8+PHBhdGggZD0iTTAgMGgxOHYxOEgweiIvPjwvZz48L3N2Zz4=);
  background-color: white;
  background-repeat: no-repeat;
  background-position: 12px 11px;
  
  &:hover {
    box-shadow: 0 -1px 0 rgba(0, 0, 0, .04), 0 2px 4px rgba(0, 0, 0, .25);
  }
  
  &:active {
    background-color: #eeeeee;
  }
  
  &:focus {
    outline: none;
    box-shadow: 
      0 -1px 0 rgba(0, 0, 0, .04),
      0 2px 4px rgba(0, 0, 0, .25),
      0 0 0 3px #c8dafc;
  }
  
  &:disabled {
    filter: grayscale(100%);
    background-color: #ebebeb;
    box-shadow: 0 -1px 0 rgba(0, 0, 0, .04), 0 1px 1px rgba(0, 0, 0, .25);
    cursor: not-allowed;
  }
}

/* GitHub
   ========================================================================== */

.btn-github,
.btn-github:visited {
    border-color: #d4d4d4;
    background: #ececec;
    background-image: -webkit-gradient(linear, 0 0, 0 100%, from(#f4f4f4), to(#ececec));
    background-image: -webkit-linear-gradient(#f4f4f4, #ececec);
    background-image: -moz-linear-gradient(#f4f4f4, #ececec);
    background-image: -ms-linear-gradient(#f4f4f4, #ececec);
    background-image: -o-linear-gradient(#f4f4f4, #ececec);
    background-image: linear-gradient(#f4f4f4, #ececec);
}

.btn-github:hover,
.btn-github:focus {
    border-color: #518cc6;
    border-bottom-color: #2a65a0;
    color: #fff;
    background-color: #599bdc;
    background-image: -webkit-gradient(linear, 0 0, 0 100%, from(#599bdc), to(#3072b3));
    background-image: -webkit-linear-gradient(#599bdc, #3072b3);
    background-image: -moz-linear-gradient(#599bdc, #3072b3);
    background-image: -ms-linear-gradient(#599bdc, #3072b3);
    background-image: -o-linear-gradient(#599bdc, #3072b3);
    background-image: linear-gradient(#599bdc, #3072b3);
}

.btn-github:active {
    border-color: #2A65A0;
    border-bottom-color: #518CC6;
    color: #fff;
    background: #3072B3;
    background: -webkit-gradient(linear, 0 0, 0 100%, from(#3072b3), to(#599bdc));
    background: -webkit-linear-gradient(#3072b3, #599bdc);
    background: -moz-linear-gradient(#3072b3, #599bdc);
    background: -ms-linear-gradient(#3072b3, #599bdc);
    background: -o-linear-gradient(#3072b3, #599bdc);
    background: linear-gradient(#3072b3, #599bdc);
}
</style>
