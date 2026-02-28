import { app } from '/scripts/app.js';

app.registerExtension({
  name: 'XYZ.TextConcatenate',
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name === 'XYZ Multi Text Concatenate') {
      const origGetExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
      nodeType.prototype.getExtraMenuOptions = function (_, options) {
        const r = origGetExtraMenuOptions?.apply?.(this, arguments);
        options.unshift(
          {
            content: 'add input',
            callback: () => {
              var index = 1;
              if (this.inputs != undefined) {
                index += this.inputs.length - 4;
              }
              this.addInput('infix ' + index, 'STRING');
              this.addOutput('PROMPT ' + index, 'STRING');
            },
          },
          {
            content: 'remove input',
            callback: () => {
              if (this.inputs != undefined) {
                this.removeInput(this.inputs.length - 1);
                this.removeOutput(this.outputs.length - 1);
              }
            },
          },
        );
        return r;
      };
    }
  },
});

app.registerExtension({
  name: 'XYZ.TextReplace',
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name === 'XYZ Multi Text Replace') {
      const origGetExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
      nodeType.prototype.getExtraMenuOptions = function (_, options) {
        const r = origGetExtraMenuOptions?.apply?.(this, arguments);
        options.unshift(
          {
            content: 'add input',
            callback: () => {
              var index = 1;
              if (this.inputs != undefined) {
                index += this.inputs.length - 1;
              }
              this.addInput('replace ' + index, 'STRING');
              this.addOutput('PROMPT ' + index, 'STRING');
            },
          },
          {
            content: 'remove input',
            callback: () => {
              if (this.inputs != undefined) {
                this.removeInput(this.inputs.length - 1);
                this.removeOutput(this.outputs.length - 1);
              }
            },
          },
        );
        return r;
      };
    }
  },
});

app.registerExtension({
  name: 'XYZ.ClipEncoder',
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name === 'XYZ Multi Clip Encoder') {
      const origGetExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
      nodeType.prototype.getExtraMenuOptions = function (_, options) {
        const r = origGetExtraMenuOptions?.apply?.(this, arguments);
        options.unshift(
          {
            content: 'add input',
            callback: () => {
              var index = 1;
              if (this.inputs != undefined) {
                index += this.inputs.length - 3;
              }
              this.addInput('extra ' + index, 'STRING');
              this.addOutput('EXTRA ' + index, 'CONDITIONING');
            },
          },
          {
            content: 'remove input',
            callback: () => {
              if (this.inputs != undefined) {
                this.removeInput(this.inputs.length - 1);
                this.removeOutput(this.outputs.length - 1);
              }
            },
          },
        );
        return r;
      };
    }
  },
});

app.registerExtension({
  name: 'XYZ.Example',
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name === 'XYZ Example') {
      const origGetExtraMenuOptions = nodeType.prototype.getExtraMenuOptions;
      nodeType.prototype.getExtraMenuOptions = function (_, options) {
        const r = origGetExtraMenuOptions?.apply?.(this, arguments);
        options.unshift(
          {
            content: 'add input',
            callback: () => {
              var index = 1;
              if (this.inputs != undefined) {
                index += this.inputs.length - 3;
              }
              this.addInput('extra ' + index, 'STRING');
              this.addOutput('EXTRA ' + index, 'CONDITIONING');
            },
          },
          {
            content: 'remove input',
            callback: () => {
              if (this.inputs != undefined) {
                this.removeInput(this.inputs.length - 1);
                this.removeOutput(this.outputs.length - 1);
              }
            },
          },
        );
        return r;
      };
    }
  },
});
