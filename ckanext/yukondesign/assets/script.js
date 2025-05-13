ckan.module("yukondesign-module", function ($, _) {
  "use strict";
  return {
    options: {
      debug: false,
    },

    initialize: function () {
      console.log("init app")
    },
  };
});
