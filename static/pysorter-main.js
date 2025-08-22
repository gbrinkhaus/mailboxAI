// globals
// var beepsound = new Audio('https://www.soundjay.com/buttons/button-11.mp3');
var maxlevels = 0;
const nerEnts = ["MISC", "PER", "ORG", "LOC"];


// To flash a message *****************************************
function flashElement(e) {
    // console.log(e);
        $(e).fadeOut(50).fadeIn(100).fadeOut(50).fadeIn(100);
    }


// To clear the *************************************
function resetApp() {
    $.ajax({
        url: '/',
        type: 'GET',
        contentType: 'application/json',
        data: JSON.stringify({ "reset": true }),
        success: function(response) { 
            location.reload();
        }, 
        error: function (error) {
            console.log(error);
        }
    });

}

function changeMoveFiles( checked ) {
    checkPathInput();

    $.ajax({
        url: '/movesettings',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ "movesetting": checked }),
        success: function(response) { 
        }, 
        error: function (error) {
            console.log(error);
        }
    });
}

// open the new tag window
function openActionWindow(actionname, action) {
    if (typeof actionname == 'undefined')
        actionname = "";
    if (typeof action == 'undefined')
        action = "";

    $("#actionTerm").attr("value", actionname);
    // $("#actionTerm").prop("value", actionname);
    $("#newAction").attr("value", action);

    modal = $('#actionModal');
    modal.modal('show');
    }


// To set target location *************************************
function setTargetDir(loc) {

    console.log(loc);

    $.ajax({
        url: '/setTargetDir',
        type: 'POST',
        contentType: "application/json",
        dataType: 'json',
        data: JSON.stringify( {'loc': loc} ),
        success: function(response) { 
            // location.reload();
        }, 
        error: function (error) { console.log(error); }
        });
};


// To open file location *************************************
function openLocation(loc, fullpath) {

    console.log(loc);

    $.ajax({
        url: '/openLocation',
        type: 'POST',
        contentType: "application/json",
        dataType: 'json',
        data: JSON.stringify( {'loc': loc, 'fullpath': fullpath} ),
            success: function(response) { 
            // location.reload();
        }, 
            error: function (error) { 
                // location.reload();
                console.log(error);
            }
        });
};


// To call OCR in Flask mopther app *************************************
// copyFile says whether the file is already in the document tree (=false, do not copy)
function callOCR(caller, copyFile = true) {
    document.getElementById("progress").innerHTML = "Please wait.";

    const payload = { 'filename': caller, 'copy': copyFile };

    function sendRequest(withPassword) {
        if (withPassword) payload.password = withPassword;
        $.ajax({
            url: '/',
            type: 'POST',
            contentType: "application/json",
            dataType: 'json',
            data: JSON.stringify(payload),
            success: function(response) {
                console.log("OCR response", response);
                // response is expected to be JSON; server returns {password_required:true} when needed
                if (response && response.password_required) {
                    // show password modal
                    showPdfPasswordModal(caller, copyFile, response.bad_password === true);
                    return;
                }
                // if copyfile, this means that we are coming from the home page
                if (copyFile) location.reload();
            },
            error: function (error) {
                console.log("OCR error", error);
            }
        });
    }

    // initial request without password
    sendRequest(null);

    // if !copyfile, this means that we are redirecting to the home page 
    if(!copyFile) {
        setTimeout(function () {
            // console.log("From documents to HP");
            window.location.pathname = "//";
        }, 3000);
        }

};


// To enable OK button in path input *************************************
function checkPathInput() {
    var disabled = true;
    if(document.getElementById('targetdir').value != "" && document.getElementById('dbdir').value != "")
        disabled = false;

    document.getElementById('pathsubmit').disabled = disabled;
};


function checkAllTagIntegrity() {
    $.ajax({
        url: '/checkAllTagIntegrity',
        type: 'POST',
        contentType: 'application/json',
        success: function(response) { }, 
        error: function (error)     { console.log(error); }
    });
};


function rebuildFilesTags() {
    $.ajax({
        url: '/rebuildFilesTags',
        type: 'POST',
        contentType: 'application/json',
        success: function(response) { },
        error: function (error)     { console.log(error); }
    });
};


// To get a tagb button group *************************************
function getTagButton(item) {
    // assuming that call is coming from btn-group or one of the children
    if(!item.classList.contains("btn-group")) {
        item = item.parentNode;
        // console.log("changed tagbutton to", item.classList);
    }

    thearray = [];
    thearray[0] = jQuery(item).find(".btn-tagpath, .btn-ner-cat")[0];
/*    if(!thearray[0])
        thearray[0] = jQuery(item).find("")[0];*/
    thearray[1] = jQuery(item).find(".btn-primary")[0];
    thearray[2] = jQuery(item).find(".btn-ner-delete")[0];

    return thearray;
};


// To write a tag into the db *************************************
// reload option is used for settings page, where it is necessary
function writeTag(text, type, hint, reload) {

    if(text == "" || type == "")
        return;

    text = text.trim().replace("\n", " ")
    type = type.trim().replace("\n", " ")

    if (typeof hint == 'undefined')
        hint = text;

    successfunc = function(response) { ; };
    if(reload)
        successfunc = function(response) { location.reload(); };

    // this is a little hack, to prevent errors when somebody should actually add a tag with my internal delimiter
    if(hint != "ACTION")
        hint = hint.trim().replace("||", "XX").replace("\n", " ")

    // console.log(text, type, hint);

    // to write the tag into database
    $.ajax({
        url: '/addTag',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ 'text': text, 'type': type, 'hint': hint }),
        success: successfunc, 
        error: function (error) {
            console.log(error);
        }
    });
};


// To write a tag into the db *************************************
function closeApp() {
    // Send shutdown request to backend
    $.ajax({
        url: '/closeApp',
        type: 'POST',
        contentType: 'application/json',
        success: function(response) {},
        error: function(error) { console.log(error); }
    });
    // Try to close the window after a short delay
    setTimeout(function() {
        window.close();
        // If window is not closed, just reload, don't show a message
        if (!window.closed) {
            location.reload();
        }
    }, 1000);
};

/* To send Flask get request, not needed right now *************************************
$(function() { $("#mybutton").click(function (event) 
{ $.getJSON('/addLevel', { }, function(data) { }); return false; }); }); */

// PDF password prompt flow
function showPdfPasswordModal(filename, copyFile, badPassword) {
    const modalEl = document.getElementById('pdfPasswordModal');
    if (!modalEl) {
        alert('This PDF is password protected.');
        return;
    }
    const pwInput = document.getElementById('pdfPasswordInput');
    const pwError = document.getElementById('pdfPasswordError');
    const submitBtn = document.getElementById('pdfPasswordSubmit');

    if (badPassword) {
        pwError.hidden = false;
    } else {
        pwError.hidden = true;
    }
    pwInput.value = '';

    // show modal using bootstrap if available
    let bsModal = null;
    if (window.bootstrap && bootstrap.Modal) {
        bsModal = new bootstrap.Modal(modalEl);
        bsModal.show();
    } else {
        modalEl.style.display = 'block';
    }

    const cleanup = () => {
        submitBtn.onclick = null;
        if (bsModal) bsModal.hide(); else modalEl.style.display = 'none';
        // clear any progress message and re-enable UI
        try {
            document.getElementById("progress").innerHTML = "";
        } catch(e) {}
    };

    submitBtn.onclick = function() {
        const pw = pwInput.value || null;
        // resend OCR with password
        document.getElementById("progress").innerHTML = "Please wait.";
        $.ajax({
            url: '/',
            type: 'POST',
            contentType: "application/json",
            dataType: 'json',
            data: JSON.stringify({ 'filename': filename, 'copy': copyFile, 'password': pw }),
            success: function(response) {
                if (response && response.password_required) {
                    // still requires password -> show error
                    showPdfPasswordModal(filename, copyFile, true);
                    return;
                }
                // success -> reload
                cleanup();
                if (copyFile) location.reload();
            },
            error: function(err) {
                console.log('Error sending password', err);
            }
        });
    };

    // wire the cancel/close buttons to cleanup so the page is not left grayed out
    try {
        const cancelBtn = modalEl.querySelector('.modal-footer .btn-secondary[data-bs-dismiss]');
        if (cancelBtn) {
            cancelBtn.onclick = function() { cleanup(); };
        }
        // if bootstrap is available, also ensure cleanup runs when the modal is hidden
        if (bsModal && bsModal._element) {
            modalEl.addEventListener('hidden.bs.modal', function () { cleanup(); });
        } else {
            // fallback: observe DOM changes to detect hide
            modalEl.addEventListener('transitionend', function() { if (modalEl.style.display === 'none') cleanup(); });
        }
    } catch(e) { /* non-fatal */ }
}
